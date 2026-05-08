import { marked, type Token, type Tokens } from 'marked';
import { wrapAsciiArt } from './asciiArt';
import { rasterizeSvgToCanvas } from './svgExportTheme';

type DocxNs = typeof import('docx');

interface InlineStyle {
  bold?: boolean;
  italics?: boolean;
}

function inlineRuns(
  d: DocxNs,
  tokens: Token[] | undefined,
  base: InlineStyle = {},
): InstanceType<DocxNs['TextRun']>[] {
  if (!tokens) return [];
  const runs: InstanceType<DocxNs['TextRun']>[] = [];
  for (const t of tokens) {
    switch (t.type) {
      case 'text': {
        const tt = t as Tokens.Text;
        if (tt.tokens && tt.tokens.length) {
          runs.push(...inlineRuns(d, tt.tokens, base));
        } else {
          runs.push(new d.TextRun({ text: tt.text, ...base }));
        }
        break;
      }
      case 'strong': {
        const tt = t as Tokens.Strong;
        runs.push(...inlineRuns(d, tt.tokens, { ...base, bold: true }));
        break;
      }
      case 'em': {
        const tt = t as Tokens.Em;
        runs.push(...inlineRuns(d, tt.tokens, { ...base, italics: true }));
        break;
      }
      case 'codespan': {
        const tt = t as Tokens.Codespan;
        runs.push(new d.TextRun({ text: tt.text, font: 'Consolas', ...base }));
        break;
      }
      case 'link': {
        const tt = t as Tokens.Link;
        runs.push(...inlineRuns(d, tt.tokens, { ...base }));
        runs.push(new d.TextRun({ text: ` (${tt.href})`, italics: true, color: '5b6470' }));
        break;
      }
      case 'br':
        runs.push(new d.TextRun({ text: '', break: 1 }));
        break;
      case 'del': {
        const tt = t as Tokens.Del;
        runs.push(...inlineRuns(d, tt.tokens, { ...base }));
        break;
      }
      default: {
        const fallback = (t as { text?: string }).text;
        if (fallback) runs.push(new d.TextRun({ text: fallback, ...base }));
      }
    }
  }
  return runs;
}

interface DiagramImage {
  buf: ArrayBuffer;
  /** Natural CSS pixel size of the source SVG. Used to compute embed aspect. */
  width: number;
  height: number;
}

const DIAGRAM_RASTER_SCALE = 4;

/**
 * Embed dimensions in CSS pixels (≈ 96 DPI). A4 portrait with 1" margins
 * gives ~6.5" × 9" of usable content. We target the full content width
 * (620px) and cap height at 860px so a tall sequence diagram still fits
 * on a single page; raster source is 4× so zooming in Word stays crisp.
 */
const DIAGRAM_TARGET_WIDTH = 620;
const DIAGRAM_MAX_HEIGHT = 860;

function canvasToArrayBuffer(canvas: HTMLCanvasElement): Promise<ArrayBuffer | null> {
  return new Promise((resolve) => {
    canvas.toBlob(
      (blob) => {
        if (!blob) return resolve(null);
        blob.arrayBuffer().then(resolve, () => resolve(null));
      },
      'image/png',
      1.0,
    );
  });
}

async function collectImages(): Promise<DiagramImage[]> {
  // Capture rendered mermaid diagrams in document order so the walker can
  // dequeue one per ```mermaid``` token it visits. Each SVG is rasterized
  // at high DPI with the shared light-theme override so the embedded image
  // is readable on a white Word page.
  const out: DiagramImage[] = [];
  const nodes = document.querySelectorAll<HTMLElement>('[data-diagram-id]');
  for (const node of Array.from(nodes)) {
    const svg = node.querySelector('svg');
    if (!svg) continue;
    const rasterized = await rasterizeSvgToCanvas(svg as SVGSVGElement, DIAGRAM_RASTER_SCALE);
    if (!rasterized) continue;
    const buf = await canvasToArrayBuffer(rasterized.canvas);
    if (!buf) continue;
    out.push({ buf, width: rasterized.width, height: rasterized.height });
  }
  return out;
}

/**
 * Size a diagram for embed. Always upscales/downscales to `targetW` so the
 * diagram fills the page width, preserving aspect. If that would make the
 * height exceed `maxH`, fall back to height-capped sizing (which yields a
 * narrower image, centered by Word's paragraph alignment).
 */
function sizeDiagramForEmbed(
  w: number,
  h: number,
  targetW: number,
  maxH: number,
): { width: number; height: number } {
  if (w <= 0 || h <= 0) return { width: targetW, height: maxH };
  const ratio = w / h;
  let width = targetW;
  let height = width / ratio;
  if (height > maxH) {
    height = maxH;
    width = height * ratio;
  }
  return { width: Math.round(width), height: Math.round(height) };
}

function asciiParagraph(d: DocxNs, text: string): InstanceType<DocxNs['Paragraph']> {
  const lines = text.replace(/\r\n/g, '\n').split('\n');
  const runs: InstanceType<DocxNs['TextRun']>[] = [];
  lines.forEach((line, i) => {
    if (i > 0) runs.push(new d.TextRun({ text: '', break: 1 }));
    runs.push(new d.TextRun({ text: line, font: 'Courier New', size: 22 }));
  });
  return new d.Paragraph({
    children: runs,
    shading: { type: d.ShadingType.SOLID, color: 'F4F1EE', fill: 'F4F1EE' },
    border: {
      top: { style: d.BorderStyle.SINGLE, size: 4, color: 'D5CFC8' },
      bottom: { style: d.BorderStyle.SINGLE, size: 4, color: 'D5CFC8' },
      left: { style: d.BorderStyle.SINGLE, size: 4, color: 'D5CFC8' },
      right: { style: d.BorderStyle.SINGLE, size: 4, color: 'D5CFC8' },
    },
    spacing: { before: 120, after: 120, line: 240 },
  });
}

function tableToDocx(d: DocxNs, token: Tokens.Table): InstanceType<DocxNs['Table']> {
  const headerCells = token.header.map(
    (h) =>
      new d.TableCell({
        children: [new d.Paragraph({ children: inlineRuns(d, h.tokens, { bold: true }) })],
        shading: { type: d.ShadingType.SOLID, color: 'EFE9E2', fill: 'EFE9E2' },
      }),
  );
  const headerRow = new d.TableRow({ children: headerCells, tableHeader: true });
  const bodyRows = token.rows.map(
    (row) =>
      new d.TableRow({
        children: row.map(
          (cell) =>
            new d.TableCell({
              children: [new d.Paragraph({ children: inlineRuns(d, cell.tokens) })],
            }),
        ),
      }),
  );
  return new d.Table({
    rows: [headerRow, ...bodyRows],
    width: { size: 100, type: d.WidthType.PERCENTAGE },
  });
}

const BLOCK_TYPES = new Set([
  'paragraph',
  'list',
  'blockquote',
  'code',
  'table',
  'heading',
  'hr',
  'space',
]);

function renderList(
  d: DocxNs,
  list: Tokens.List,
  depth: number,
  imageQueue: DiagramImage[],
): Array<InstanceType<DocxNs['Paragraph']> | InstanceType<DocxNs['Table']>> {
  const out: Array<InstanceType<DocxNs['Paragraph']> | InstanceType<DocxNs['Table']>> = [];
  const indent = 360 + depth * 360;
  const bullet = depth % 2 === 0 ? '•' : '◦';
  for (let i = 0; i < list.items.length; i++) {
    const item = list.items[i];
    const prefix = list.ordered ? `${i + 1}.` : bullet;
    const inlineToks: Token[] = [];
    const blockToks: Token[] = [];
    for (const child of item.tokens || []) {
      if (BLOCK_TYPES.has(child.type)) blockToks.push(child);
      else inlineToks.push(child);
    }
    // Marked emits leading body text inside list items as a block-level
    // 'text' token whose `.tokens` carries the inline runs. Treat that as
    // the bullet's primary line so we don't lose it.
    let primaryInline = inlineToks;
    const remainingBlocks: Token[] = [];
    for (const block of blockToks) {
      if (
        block.type === 'paragraph' ||
        (block.type === 'text' && (block as Tokens.Text).tokens)
      ) {
        if (primaryInline.length === 0) {
          primaryInline = (block as Tokens.Paragraph | Tokens.Text).tokens || [];
          continue;
        }
      }
      remainingBlocks.push(block);
    }
    out.push(
      new d.Paragraph({
        children: [
          new d.TextRun({ text: `${prefix}  ` }),
          ...inlineRuns(d, primaryInline),
        ],
        indent: { left: indent },
      }),
    );
    for (const block of remainingBlocks) {
      if (block.type === 'list') {
        out.push(...renderList(d, block as Tokens.List, depth + 1, imageQueue));
      } else if (block.type === 'paragraph') {
        out.push(
          new d.Paragraph({
            children: inlineRuns(d, (block as Tokens.Paragraph).tokens),
            indent: { left: indent + 360 },
          }),
        );
      } else {
        out.push(...walkTokens(d, [block], imageQueue));
      }
    }
  }
  return out;
}

function walkTokens(
  d: DocxNs,
  tokens: Token[],
  imageQueue: DiagramImage[],
): Array<InstanceType<DocxNs['Paragraph']> | InstanceType<DocxNs['Table']>> {
  const out: Array<InstanceType<DocxNs['Paragraph']> | InstanceType<DocxNs['Table']>> = [];
  const HEADINGS: Record<number, (typeof d.HeadingLevel)[keyof typeof d.HeadingLevel]> = {
    1: d.HeadingLevel.HEADING_1,
    2: d.HeadingLevel.HEADING_2,
    3: d.HeadingLevel.HEADING_3,
    4: d.HeadingLevel.HEADING_4,
    5: d.HeadingLevel.HEADING_5,
    6: d.HeadingLevel.HEADING_6,
  };
  let imgIdx = 0;
  for (const tok of tokens) {
    switch (tok.type) {
      case 'heading': {
        const t = tok as Tokens.Heading;
        out.push(
          new d.Paragraph({
            heading: HEADINGS[t.depth] || d.HeadingLevel.HEADING_3,
            children: inlineRuns(d, t.tokens),
          }),
        );
        break;
      }
      case 'paragraph': {
        const t = tok as Tokens.Paragraph;
        out.push(new d.Paragraph({ children: inlineRuns(d, t.tokens) }));
        break;
      }
      case 'blockquote': {
        const t = tok as Tokens.Blockquote;
        out.push(
          new d.Paragraph({
            children: inlineRuns(d, t.tokens, { italics: true }),
            indent: { left: 360 },
            border: {
              left: { style: d.BorderStyle.SINGLE, size: 12, color: 'C9602F', space: 8 },
            },
          }),
        );
        break;
      }
      case 'list': {
        out.push(...renderList(d, tok as Tokens.List, 0, imageQueue));
        break;
      }
      case 'code': {
        const t = tok as Tokens.Code;
        if (t.lang === 'mermaid') {
          const image = imageQueue[imgIdx++];
          if (image) {
            const { width, height } = sizeDiagramForEmbed(
              image.width,
              image.height,
              DIAGRAM_TARGET_WIDTH,
              DIAGRAM_MAX_HEIGHT,
            );
            out.push(
              new d.Paragraph({
                alignment: d.AlignmentType.CENTER,
                children: [
                  new d.ImageRun({
                    type: 'png',
                    data: image.buf,
                    transformation: { width, height },
                  }),
                ],
              }),
            );
          } else {
            out.push(asciiParagraph(d, t.text));
          }
        } else {
          out.push(asciiParagraph(d, t.text));
        }
        break;
      }
      case 'table':
        out.push(tableToDocx(d, tok as Tokens.Table));
        out.push(new d.Paragraph({ children: [] }));
        break;
      case 'hr':
        out.push(
          new d.Paragraph({
            children: [],
            border: {
              bottom: { style: d.BorderStyle.SINGLE, size: 6, color: 'D5CFC8' },
            },
          }),
        );
        break;
      case 'space':
        out.push(new d.Paragraph({ children: [] }));
        break;
      default: {
        const fallback = (tok as { text?: string }).text;
        if (fallback) out.push(new d.Paragraph({ children: [new d.TextRun({ text: fallback })] }));
      }
    }
  }
  return out;
}

export async function exportMarkdownToDocx(
  markdown: string,
  filename: string,
  opts: { title?: string } = {},
): Promise<void> {
  const docx = await import('docx');
  const prepared = wrapAsciiArt(markdown);
  const tokens = marked.lexer(prepared);
  const images = await collectImages();
  const children: Array<InstanceType<DocxNs['Paragraph']> | InstanceType<DocxNs['Table']>> = [];
  if (opts.title) {
    children.push(
      new docx.Paragraph({
        heading: docx.HeadingLevel.TITLE,
        children: [new docx.TextRun({ text: opts.title })],
      }),
    );
  }
  children.push(...walkTokens(docx, tokens, images));

  const doc = new docx.Document({
    creator: 'AlignIQ',
    title: opts.title || 'Report',
    sections: [{ properties: {}, children }],
  });
  const blob = await docx.Packer.toBlob(doc);
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
