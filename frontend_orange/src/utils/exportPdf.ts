import { rasterizeSvgToCanvas } from './svgExportTheme';

/**
 * Render a report DOM node to a multi-page A4 PDF intended as a sharable
 * business document.
 *
 * What this produces:
 *
 * - **Cover page** with brand mark, document title, and generation date.
 *   Drawn with native jsPDF text/shape APIs — vector, crisp at any zoom.
 * - **Content pages** rasterized from the live (dark-themed) report DOM
 *   that's been deep-cloned into an off-screen wrap with CSS-custom-
 *   property overrides flipping the report to high-contrast colors.
 *   Mermaid SVGs are pre-rasterized at 3× with a light-theme override
 *   stylesheet injected into the SVG itself, so diagram text stays dark
 *   and readable on a white page.
 * - **Page chrome** (top brand strip + bottom title/page-number footer)
 *   on every content page, drawn natively after pagination so totals are
 *   accurate.
 * - **Page-aware slicing**: before slicing, we collect Y offsets of every
 *   block boundary (h1–h6, p, li, tr, table, blockquote, pre, .diagram-
 *   block, hr, ul, ol). Each page ends at the largest break point that
 *   still fits on the page, so headings/tables/diagrams are never sliced
 *   through. Hard cuts are reserved for blocks that exceed a full page.
 */

const PDF_VAR_OVERRIDES: Record<string, string> = {
  '--bg': '#ffffff',
  '--bg-2': '#ffffff',
  '--surface': '#ffffff',
  '--surface-2': '#faf7f2',
  '--border': '#d8d3cb',
  '--border-strong': '#c8c2b8',
  '--fg': '#111111',
  '--fg-dim': '#333333',
  '--fg-muted': '#555555',
  '--accent': '#b25a1f',
  '--accent-2': '#c87a3f',
  '--accent-soft': '#f4e7df',
  '--shadow-lg': 'none',
  '--glow': 'none',
};

/**
 * Wrap is 820px wide with 36px horizontal padding → 748px content area.
 * Force every diagram to fill this width (with a height cap so a tall
 * sequence diagram still fits on one A4 page) and bump the raster scale to
 * 4× so even after the html2canvas snapshot at 2× the embedded image still
 * has > 3× device-pixel ratio when zoomed in a PDF viewer.
 */
const SVG_RASTER_SCALE = 4;
const DIAGRAM_TARGET_WIDTH = 720;
const DIAGRAM_MAX_HEIGHT = 980;

const BREAK_SELECTORS = [
  'h1',
  'h2',
  'h3',
  'h4',
  'h5',
  'h6',
  'p',
  'li',
  'tr',
  'thead',
  'tbody',
  'table',
  'blockquote',
  'pre',
  '.diagram-block',
  'hr',
  'ul',
  'ol',
];

/* Brand palette in jsPDF RGB tuples. */
const BRAND_ACCENT: [number, number, number] = [178, 90, 31]; // #b25a1f
const BRAND_ACCENT_SOFT: [number, number, number] = [200, 122, 63]; // #c87a3f
const TEXT_DARK: [number, number, number] = [17, 17, 17];
const TEXT_MUTED: [number, number, number] = [110, 110, 110];
const RULE_LIGHT: [number, number, number] = [216, 211, 203];

const MARGIN = 44;
const HEADER_BAND = 28;
const FOOTER_BAND = 28;

/** Replace every <svg> in `root` with a high-DPI <img> using the light theme. */
async function inlineRasterizeSvgs(root: HTMLElement): Promise<void> {
  const svgs = Array.from(root.querySelectorAll('svg'));
  await Promise.all(
    svgs.map(async (svg) => {
      const rasterized = await rasterizeSvgToCanvas(svg as SVGSVGElement, SVG_RASTER_SCALE);
      if (!rasterized) return;
      const aspect = rasterized.width / rasterized.height;
      let displayW = DIAGRAM_TARGET_WIDTH;
      let displayH = displayW / aspect;
      if (displayH > DIAGRAM_MAX_HEIGHT) {
        displayH = DIAGRAM_MAX_HEIGHT;
        displayW = displayH * aspect;
      }
      const dataUrl = rasterized.canvas.toDataURL('image/png');
      const replacement = document.createElement('img');
      replacement.src = dataUrl;
      replacement.style.width = `${Math.round(displayW)}px`;
      replacement.style.height = `${Math.round(displayH)}px`;
      replacement.style.display = 'block';
      replacement.style.maxWidth = '100%';
      replacement.style.margin = '12px auto';
      replacement.style.background = '#ffffff';
      replacement.style.border = '1px solid #d8d3cb';
      replacement.style.padding = '8px';
      replacement.style.boxSizing = 'border-box';
      await new Promise<void>((resolve) => {
        replacement.onload = () => resolve();
        replacement.onerror = () => resolve();
      });
      svg.replaceWith(replacement);
    }),
  );
}

/** Break-point Y offsets relative to `root`, in CSS pixels, sorted ascending. */
function collectBreakPoints(root: HTMLElement): number[] {
  const rootTop = root.getBoundingClientRect().top;
  const points = new Set<number>([0]);
  for (const sel of BREAK_SELECTORS) {
    const list = root.querySelectorAll(sel);
    for (const el of Array.from(list)) {
      const r = (el as HTMLElement).getBoundingClientRect();
      points.add(Math.max(0, Math.round(r.top - rootTop)));
      points.add(Math.max(0, Math.round(r.top + r.height - rootTop)));
    }
  }
  points.add(root.scrollHeight);
  return Array.from(points).sort((a, b) => a - b);
}

function drawCoverPage(
  pdf: import('jspdf').jsPDF,
  title: string,
  pageWidth: number,
  pageHeight: number,
): void {
  // Top accent bar
  pdf.setFillColor(...BRAND_ACCENT);
  pdf.rect(0, 0, pageWidth, 6, 'F');

  // Brand mark
  pdf.setFont('helvetica', 'bold');
  pdf.setFontSize(11);
  pdf.setTextColor(...BRAND_ACCENT);
  pdf.text('ALIGNIQ', MARGIN, 56);

  // Document type label
  pdf.setFont('helvetica', 'normal');
  pdf.setFontSize(8.5);
  pdf.setTextColor(...TEXT_MUTED);
  pdf.text('TECHNICAL ANALYSIS REPORT', MARGIN, 70);

  // Centered title block
  const titleY = pageHeight / 2 - 60;
  pdf.setDrawColor(...BRAND_ACCENT);
  pdf.setLineWidth(2);
  pdf.line(MARGIN, titleY - 24, MARGIN + 60, titleY - 24);

  pdf.setFont('helvetica', 'bold');
  pdf.setFontSize(28);
  pdf.setTextColor(...TEXT_DARK);
  const titleLines = pdf.splitTextToSize(title || 'Project Report', pageWidth - MARGIN * 2);
  pdf.text(titleLines, MARGIN, titleY);

  // Subhead
  pdf.setFont('helvetica', 'normal');
  pdf.setFontSize(11);
  pdf.setTextColor(...TEXT_MUTED);
  pdf.text(
    'Generated by the AlignIQ multi-agent analysis pipeline.',
    MARGIN,
    titleY + (titleLines.length * 30) + 14,
  );

  // Footer block
  pdf.setDrawColor(...RULE_LIGHT);
  pdf.setLineWidth(0.5);
  pdf.line(MARGIN, pageHeight - 90, pageWidth - MARGIN, pageHeight - 90);

  const date = new Date().toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });
  pdf.setFont('helvetica', 'bold');
  pdf.setFontSize(8.5);
  pdf.setTextColor(...TEXT_MUTED);
  pdf.text('GENERATED', MARGIN, pageHeight - 70);
  pdf.setFont('helvetica', 'normal');
  pdf.setFontSize(11);
  pdf.setTextColor(...TEXT_DARK);
  pdf.text(date, MARGIN, pageHeight - 54);

  pdf.setFont('helvetica', 'bold');
  pdf.setFontSize(8.5);
  pdf.setTextColor(...TEXT_MUTED);
  pdf.text('CLASSIFICATION', pageWidth / 2, pageHeight - 70);
  pdf.setFont('helvetica', 'normal');
  pdf.setFontSize(11);
  pdf.setTextColor(...TEXT_DARK);
  pdf.text('Internal · Client-shareable', pageWidth / 2, pageHeight - 54);

  // Bottom accent bar
  pdf.setFillColor(...BRAND_ACCENT);
  pdf.rect(0, pageHeight - 6, pageWidth, 6, 'F');
}

function drawPageChrome(
  pdf: import('jspdf').jsPDF,
  pageNum: number,
  totalContentPages: number,
  title: string,
  pageWidth: number,
  pageHeight: number,
): void {
  // Top brand band
  pdf.setFillColor(...BRAND_ACCENT);
  pdf.rect(0, 0, pageWidth, 3, 'F');
  pdf.setFont('helvetica', 'bold');
  pdf.setFontSize(8);
  pdf.setTextColor(...BRAND_ACCENT);
  pdf.text('ALIGNIQ', MARGIN, 18);

  // Top right: truncated title
  pdf.setFont('helvetica', 'normal');
  pdf.setFontSize(8);
  pdf.setTextColor(...TEXT_MUTED);
  const trunc = title.length > 70 ? `${title.slice(0, 70)}…` : title;
  pdf.text(trunc, pageWidth - MARGIN, 18, { align: 'right' });

  pdf.setDrawColor(...RULE_LIGHT);
  pdf.setLineWidth(0.4);
  pdf.line(MARGIN, 24, pageWidth - MARGIN, 24);

  // Footer
  pdf.line(MARGIN, pageHeight - 26, pageWidth - MARGIN, pageHeight - 26);
  pdf.setFont('helvetica', 'normal');
  pdf.setFontSize(8);
  pdf.setTextColor(...TEXT_MUTED);
  pdf.text('AlignIQ · Generated Report', MARGIN, pageHeight - 14);
  pdf.setFont('helvetica', 'bold');
  pdf.setTextColor(...BRAND_ACCENT_SOFT);
  pdf.text(`${pageNum} / ${totalContentPages}`, pageWidth - MARGIN, pageHeight - 14, {
    align: 'right',
  });
}

export async function exportNodeToPdf(
  node: HTMLElement,
  filename: string,
  opts: { title?: string } = {},
): Promise<void> {
  const [{ default: html2canvas }, { jsPDF }] = await Promise.all([
    import('html2canvas'),
    import('jspdf'),
  ]);

  const wrap = document.createElement('div');
  wrap.className = 'pdf-export-root';
  wrap.style.cssText =
    'position: fixed; left: -10000px; top: 0; width: 820px; background: #ffffff; color: #111111; padding: 24px 36px; z-index: -1;';
  for (const [name, value] of Object.entries(PDF_VAR_OVERRIDES)) {
    wrap.style.setProperty(name, value, 'important');
  }
  wrap.appendChild(node.cloneNode(true));
  document.body.appendChild(wrap);

  try {
    await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
    await inlineRasterizeSvgs(wrap);
    await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));

    const breakPointsCss = collectBreakPoints(wrap);

    const snapshotScale = 2;
    const canvas = await html2canvas(wrap, {
      scale: snapshotScale,
      useCORS: true,
      logging: false,
      backgroundColor: '#ffffff',
    });

    const cssToCanvasY = canvas.height / wrap.offsetHeight;
    const breakPointsCanvas = breakPointsCss
      .map((y) => Math.round(y * cssToCanvasY))
      .filter((y) => y >= 0 && y <= canvas.height);
    if (!breakPointsCanvas.includes(canvas.height)) breakPointsCanvas.push(canvas.height);

    const pdf = new jsPDF({ unit: 'pt', format: 'a4', orientation: 'portrait' });
    const pageWidth = pdf.internal.pageSize.getWidth();
    const pageHeight = pdf.internal.pageSize.getHeight();
    const title = opts.title?.trim() || 'Project Report';

    // Cover page first.
    drawCoverPage(pdf, title, pageWidth, pageHeight);

    const contentTop = HEADER_BAND + 8;
    const contentBottom = pageHeight - FOOTER_BAND - 8;
    const contentHeight = contentBottom - contentTop;
    const contentWidth = pageWidth - MARGIN * 2;
    const imgWidth = contentWidth;
    const maxSliceHeightPx = contentHeight * (canvas.width / contentWidth);

    let renderedPx = 0;
    const contentPageStarts: number[] = [];
    while (renderedPx < canvas.height) {
      const target = renderedPx + maxSliceHeightPx;
      let sliceEnd = renderedPx;
      for (const bp of breakPointsCanvas) {
        if (bp > renderedPx && bp <= target && bp > sliceEnd) sliceEnd = bp;
      }
      if (sliceEnd === renderedPx) {
        sliceEnd = Math.min(target, canvas.height);
      }
      const sliceHeight = Math.max(1, sliceEnd - renderedPx);

      const sliceCanvas = document.createElement('canvas');
      sliceCanvas.width = canvas.width;
      sliceCanvas.height = sliceHeight;
      const ctx = sliceCanvas.getContext('2d');
      if (!ctx) break;
      ctx.fillStyle = '#ffffff';
      ctx.fillRect(0, 0, sliceCanvas.width, sliceCanvas.height);
      ctx.drawImage(
        canvas,
        0,
        renderedPx,
        canvas.width,
        sliceHeight,
        0,
        0,
        sliceCanvas.width,
        sliceCanvas.height,
      );
      const dataUrl = sliceCanvas.toDataURL('image/jpeg', 0.94);
      pdf.addPage();
      const sliceHeightPt = (sliceHeight * imgWidth) / canvas.width;
      pdf.addImage(dataUrl, 'JPEG', MARGIN, contentTop, imgWidth, sliceHeightPt);
      contentPageStarts.push(renderedPx);
      renderedPx = sliceEnd;
    }

    // Apply chrome to content pages now that we know the total.
    const totalContentPages = contentPageStarts.length;
    for (let i = 0; i < totalContentPages; i++) {
      pdf.setPage(2 + i); // page 1 = cover
      drawPageChrome(pdf, i + 1, totalContentPages, title, pageWidth, pageHeight);
    }

    pdf.save(filename);
  } finally {
    wrap.remove();
  }
}
