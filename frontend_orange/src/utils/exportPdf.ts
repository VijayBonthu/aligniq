import { marked, type Token, type Tokens } from 'marked';
import { wrapAsciiArt } from './asciiArt';
import { normalizeDiagramFences } from './markdown';
import { rasterizeSvgToCanvas } from './svgExportTheme';

/**
 * Vector PDF export.
 *
 * This does NOT screenshot the DOM. It rebuilds the report from the markdown
 * with pdfmake, so the body is real vector text — sharp at any zoom, selectable,
 * searchable, copyable, with clickable citation links — exactly like a
 * production-generated document. Tables, lists, wrapping, pagination and page
 * chrome are all native pdfmake (vector).
 *
 * Diagrams: mermaid styles its SVGs with a <style> block, which client-side
 * SVG→PDF converters ignore (colors come out wrong). The browser is the only
 * client-side engine that renders mermaid correctly, so each diagram is
 * rasterized by the browser at high DPI (4×) with the light-theme override and
 * embedded as a crisp, zoomable image. (Truly-infinite-vector diagrams require
 * server-side headless Chrome — a separate, heavier path.)
 */

const ACCENT = '#b25a1f';
const FG = '#1c1c1c';
const FG_DIM = '#3a3a3a';
const FG_MUTED = '#6b6b6b';
const RULE = '#d8d3cb';
const CODE_BG = '#f4f1ec';

const DIAGRAM_RASTER_SCALE = 4;
// A4 content box in pt with the margins below: 595.28 - 96 ≈ 499 wide,
// 841.89 - 120 ≈ 722 tall.
const CONTENT_WIDTH_PT = 499;
const CONTENT_HEIGHT_PT = 700;

type PdfContent = any; // pdfmake content nodes — kept loose to avoid type churn.

interface DiagramImage {
  dataUrl: string;
  width: number;
  height: number;
}

/**
 * Collect rendered mermaid diagrams from the report node in document order and
 * rasterize each (browser-rendered, light-themed, high DPI) to a PNG data URL,
 * so the walker can dequeue one per ```mermaid``` token it meets.
 */
async function collectDiagramImages(node: HTMLElement | null): Promise<DiagramImage[]> {
  if (!node) return [];
  const out: DiagramImage[] = [];
  const blocks = node.querySelectorAll<HTMLElement>('[data-diagram-id]');
  for (const block of Array.from(blocks)) {
    const svg = block.querySelector('svg');
    if (!svg) continue;
    const r = await rasterizeSvgToCanvas(svg as unknown as SVGSVGElement, DIAGRAM_RASTER_SCALE);
    if (!r) continue;
    out.push({ dataUrl: r.canvas.toDataURL('image/png'), width: r.width, height: r.height });
  }
  return out;
}

/** Map marked inline tokens to pdfmake styled text runs. */
function inline(tokens: Token[] | undefined, base: Record<string, unknown> = {}): PdfContent[] {
  if (!tokens) return [];
  const runs: PdfContent[] = [];
  for (const t of tokens) {
    switch (t.type) {
      case 'text': {
        const tt = t as Tokens.Text;
        if (tt.tokens && tt.tokens.length) runs.push(...inline(tt.tokens, base));
        else runs.push({ text: tt.text, ...base });
        break;
      }
      case 'strong':
        runs.push(...inline((t as Tokens.Strong).tokens, { ...base, bold: true }));
        break;
      case 'em':
        runs.push(...inline((t as Tokens.Em).tokens, { ...base, italics: true }));
        break;
      case 'codespan':
        runs.push({ text: (t as Tokens.Codespan).text, color: ACCENT, ...base });
        break;
      case 'link': {
        const tt = t as Tokens.Link;
        const label = tt.tokens && tt.tokens.length ? tt.tokens.map((x) => (x as { text?: string }).text ?? '').join('') : tt.text;
        runs.push({ text: label || tt.href, link: tt.href, color: ACCENT, decoration: 'underline', ...base });
        break;
      }
      case 'br':
        runs.push({ text: '\n', ...base });
        break;
      case 'del':
        runs.push(...inline((t as Tokens.Del).tokens, { ...base, decoration: 'lineThrough' }));
        break;
      case 'codespan ': // never
        break;
      default: {
        const fb = (t as { text?: string }).text;
        if (fb) runs.push({ text: fb, ...base });
      }
    }
  }
  return runs.length ? runs : [{ text: '', ...base }];
}

const HEADING_STYLE: Record<number, { fontSize: number; color: string; bold: boolean; top: number; bottom: number }> = {
  1: { fontSize: 22, color: FG, bold: true, top: 4, bottom: 10 },
  2: { fontSize: 16, color: FG, bold: true, top: 16, bottom: 7 },
  3: { fontSize: 13, color: ACCENT, bold: true, top: 12, bottom: 5 },
  4: { fontSize: 11, color: FG_MUTED, bold: true, top: 10, bottom: 4 },
  5: { fontSize: 10.5, color: FG_MUTED, bold: true, top: 8, bottom: 3 },
  6: { fontSize: 10, color: FG_MUTED, bold: true, top: 8, bottom: 3 },
};

/**
 * Insert zero-width break opportunities so pdfmake can wrap long unbreakable
 * tokens inside narrow table columns (version strings, scoped package names,
 * paths, URLs). Without this, one over-wide column pushes the table past the
 * page width and the rightmost column(s) get clipped in the PDF.
 */
function softBreak(s: string): string {
  const ZWSP = '​';
  return s
    .replace(/([/_\-.@:,;\\])/g, `$1${ZWSP}`) // break right after common separators
    .replace(/(\S{14})(?=\S)/g, `$1${ZWSP}`); // and inside very long unbroken runs
}

function softBreakRuns(runs: PdfContent[]): PdfContent[] {
  return runs.map((r) =>
    r && typeof r.text === 'string' ? { ...r, text: softBreak(r.text) } : r,
  );
}

function tableCell(tokens: Token[] | undefined, header: boolean): PdfContent {
  return {
    text: softBreakRuns(inline(tokens, header ? { bold: true } : {})),
    fillColor: header ? '#efe9e2' : undefined,
    margin: [3, 2, 3, 2],
    fontSize: 8,
  };
}

function listItems(list: Tokens.List, images: DiagramImage[], idx: { i: number }): PdfContent[] {
  return list.items.map((item) => {
    const inlineToks: Token[] = [];
    const blockToks: Token[] = [];
    for (const child of item.tokens || []) {
      if (['list', 'table', 'code', 'blockquote', 'heading', 'space', 'hr'].includes(child.type)) blockToks.push(child);
      else if (child.type === 'text' && (child as Tokens.Text).tokens) inlineToks.push(...((child as Tokens.Text).tokens || []));
      else if (child.type === 'paragraph') inlineToks.push(...((child as Tokens.Paragraph).tokens || []));
      else inlineToks.push(child);
    }
    const lead: PdfContent = { text: inline(inlineToks) };
    if (!blockToks.length) return lead;
    return { stack: [lead, ...walk(blockToks, images, idx)] };
  });
}

function walk(tokens: Token[], images: DiagramImage[], idx: { i: number }): PdfContent[] {
  const out: PdfContent[] = [];
  for (const tok of tokens) {
    switch (tok.type) {
      case 'heading': {
        const t = tok as Tokens.Heading;
        const s = HEADING_STYLE[t.depth] || HEADING_STYLE[6];
        out.push({
          text: inline(t.tokens),
          fontSize: s.fontSize,
          bold: s.bold,
          color: s.color,
          margin: [0, s.top, 0, s.bottom],
        });
        break;
      }
      case 'paragraph':
        out.push({ text: inline((tok as Tokens.Paragraph).tokens), margin: [0, 0, 0, 8], lineHeight: 1.3 });
        break;
      case 'blockquote':
        out.push({
          margin: [0, 4, 0, 10],
          table: {
            widths: [3, '*'],
            body: [[
              { text: '', fillColor: ACCENT },
              { stack: walk((tok as Tokens.Blockquote).tokens, images, idx), margin: [8, 4, 4, 4], color: FG_DIM, italics: true },
            ]],
          },
          layout: 'noBorders',
        });
        break;
      case 'list': {
        const t = tok as Tokens.List;
        const items = listItems(t, images, idx);
        out.push({ [t.ordered ? 'ol' : 'ul']: items, margin: [4, 0, 0, 8], lineHeight: 1.25 } as PdfContent);
        break;
      }
      case 'code': {
        const t = tok as Tokens.Code;
        const lang = (t.lang ?? '').trim().split(/\s+/)[0];
        if (lang === 'mermaid' || lang === 'ascii') {
          const img = images[idx.i++];
          if (img) {
            const aspect = img.width / img.height || 1;
            let w = Math.min(CONTENT_WIDTH_PT, img.width);
            if (w / aspect > CONTENT_HEIGHT_PT) w = CONTENT_HEIGHT_PT * aspect;
            out.push({ image: img.dataUrl, width: w, alignment: 'center', margin: [0, 6, 0, 12] });
            break;
          }
          // No rendered image (failed diagram): fall through to source text.
        }
        out.push({
          text: t.text,
          fontSize: 8.5,
          color: FG_DIM,
          preserveLeadingSpaces: true,
          fillColor: CODE_BG,
          margin: [0, 4, 0, 10],
        });
        break;
      }
      case 'table': {
        const t = tok as Tokens.Table;
        const body: PdfContent[][] = [];
        body.push(t.header.map((h) => tableCell(h.tokens, true)));
        for (const row of t.rows) body.push(row.map((c) => tableCell(c.tokens, false)));
        out.push({
          table: { headerRows: 1, widths: t.header.map(() => '*'), body, dontBreakRows: true },
          layout: {
            hLineWidth: () => 0.5,
            vLineWidth: () => 0.5,
            hLineColor: () => RULE,
            vLineColor: () => RULE,
          },
          margin: [0, 4, 0, 12],
          fontSize: 9,
        });
        break;
      }
      case 'hr':
        out.push({ canvas: [{ type: 'line', x1: 0, y1: 0, x2: CONTENT_WIDTH_PT, y2: 0, lineWidth: 0.5, lineColor: RULE }], margin: [0, 8, 0, 12] });
        break;
      case 'space':
        break;
      default: {
        const fb = (tok as { text?: string }).text;
        if (fb && fb.trim()) out.push({ text: fb, margin: [0, 0, 0, 8] });
      }
    }
  }
  return out;
}

function coverPage(title: string): PdfContent {
  const date = new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' });
  return {
    stack: [
      { text: 'ALIGNIQ', color: ACCENT, bold: true, fontSize: 12, margin: [0, 120, 0, 0] },
      { text: 'TECHNICAL ANALYSIS REPORT', color: FG_MUTED, fontSize: 9, characterSpacing: 1, margin: [0, 6, 0, 36] },
      { canvas: [{ type: 'line', x1: 0, y1: 0, x2: 60, y2: 0, lineWidth: 2, lineColor: ACCENT }], margin: [0, 0, 0, 18] },
      { text: title, fontSize: 27, bold: true, color: FG, margin: [0, 0, 0, 14] },
      { text: 'Generated by the AlignIQ multi-agent analysis pipeline.', color: FG_MUTED, fontSize: 11 },
      { text: `Generated ${date}`, color: FG_MUTED, fontSize: 9, margin: [0, 36, 0, 0] },
    ],
    pageBreak: 'after',
  };
}

export async function exportMarkdownToPdf(
  markdown: string,
  filename: string,
  opts: { title?: string; node?: HTMLElement | null } = {},
): Promise<void> {
  const title = opts.title?.trim() || 'Project Report';

  const [pdfMakeMod, vfsMod] = await Promise.all([
    import('pdfmake/build/pdfmake'),
    import('pdfmake/build/vfs_fonts'),
  ]);
  /* eslint-disable @typescript-eslint/no-explicit-any */
  const pdfMake: any = (pdfMakeMod as any).default ?? pdfMakeMod;

  // Locate the {filename: base64} font map regardless of how the bundler exposed
  // the module (0.2.x nested it under .pdfMake.vfs; 0.3.x exports the map itself;
  // ESM interop may wrap it under .default).
  // Must check the VALUE is real base64 data, not just that a *.ttf key exists:
  // Vite's CJS interop can expose the namespace with .ttf keys whose values are
  // undefined (the real data lives on .default), which would make pdfmake do
  // Buffer.from(undefined) → "first argument must be ... Received type undefined".
  const findVfs = (m: any): any => {
    for (const c of [m?.default, m, m?.vfs, m?.default?.vfs, m?.pdfMake?.vfs, m?.default?.pdfMake?.vfs]) {
      if (
        c &&
        typeof c === 'object' &&
        Object.entries(c).some(
          ([k, val]) => k.toLowerCase().endsWith('.ttf') && typeof val === 'string' && val.length > 100,
        )
      ) {
        return c;
      }
    }
    return undefined;
  };
  const vfs = findVfs(vfsMod);
  // 0.3.x browser API is addVirtualFileSystem(); .vfs is the 0.2.x fallback.
  if (vfs) {
    if (typeof pdfMake.addVirtualFileSystem === 'function') pdfMake.addVirtualFileSystem(vfs);
    pdfMake.vfs = vfs;
  }
  /* eslint-enable @typescript-eslint/no-explicit-any */

  const images = await collectDiagramImages(opts.node ?? null);
  const tokens = marked.lexer(wrapAsciiArt(normalizeDiagramFences(markdown)));
  const body = walk(tokens, images, { i: 0 });

  const docDefinition: PdfContent = {
    pageSize: 'A4',
    pageMargins: [48, 54, 48, 48],
    info: { title, creator: 'AlignIQ' },
    defaultStyle: { fontSize: 10.5, color: FG, lineHeight: 1.25 },
    content: [coverPage(title), ...body],
    footer: (currentPage: number, pageCount: number): PdfContent => {
      if (currentPage === 1) return null;
      return {
        margin: [48, 12, 48, 0],
        columns: [
          { text: 'AlignIQ · Generated Report', fontSize: 8, color: FG_MUTED },
          { text: `${currentPage - 1} / ${pageCount - 1}`, fontSize: 8, color: ACCENT, alignment: 'right' },
        ],
      };
    },
    header: (currentPage: number): PdfContent => {
      if (currentPage === 1) return null;
      return {
        margin: [48, 18, 48, 0],
        columns: [
          { text: 'ALIGNIQ', fontSize: 8, bold: true, color: ACCENT },
          { text: title.length > 70 ? `${title.slice(0, 70)}…` : title, fontSize: 8, color: FG_MUTED, alignment: 'right' },
        ],
      };
    },
  };

  // pdfmake 0.3.x download() returns a Promise; 0.2.x returns undefined and
  // triggers the download synchronously. Await only when it's thenable.
  const ret = pdfMake.createPdf(docDefinition).download(filename);
  if (ret && typeof ret.then === 'function') await ret;
}
