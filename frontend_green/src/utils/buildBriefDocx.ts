/**
 * Packages a typed project brief (title + Markdown-ish body + screenshots) into a
 * real .docx File that the existing `/upload` endpoint already understands.
 *
 * Why .docx and not .md: the backend's `ExtractText.extract_docx()` pulls the
 * paragraph text AND runs a vision summariser (`summarize_image`) on every
 * embedded image — so pasted screenshots become parseable signal for free. A
 * `.md` upload is read verbatim by `_process_txt`, which would turn embedded
 * image data into noise. So the typed path mirrors the file-upload path exactly,
 * with no backend change.
 */

export interface BriefScreenshot {
  /** PNG data URL (normalised on capture). */
  dataUrl: string;
  /** Natural pixel size of the (already downscaled) PNG. */
  width: number;
  height: number;
  caption: string;
}

export interface BriefDraft {
  title: string;
  body: string;
  screenshots: BriefScreenshot[];
}

const DOCX_MIME =
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document';

/** A .docx filename is split on '.' by the backend, so keep the stem dot-free. */
function safeStem(title: string): string {
  const cleaned = title
    .trim()
    .replace(/[^\w\s-]+/g, '')
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '')
    .slice(0, 60);
  return cleaned || 'project-brief';
}

function dataUrlToBytes(dataUrl: string): Uint8Array {
  const base64 = dataUrl.slice(dataUrl.indexOf(',') + 1);
  const bin = atob(base64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i += 1) bytes[i] = bin.charCodeAt(i);
  return bytes;
}

/** Embed at most this CSS-pixel width; preserve aspect. */
const IMAGE_MAX_WIDTH = 600;

type DocxNs = typeof import('docx');

function bodyParagraphs(
  d: DocxNs,
  body: string,
): InstanceType<DocxNs['Paragraph']>[] {
  const out: InstanceType<DocxNs['Paragraph']>[] = [];
  const lines = body.replace(/\r\n/g, '\n').split('\n');
  for (const raw of lines) {
    const line = raw.trimEnd();
    if (!line.trim()) {
      out.push(new d.Paragraph({ children: [] }));
      continue;
    }
    const h = /^(#{1,3})\s+(.*)$/.exec(line);
    if (h) {
      const level =
        h[1].length === 1
          ? d.HeadingLevel.HEADING_1
          : h[1].length === 2
          ? d.HeadingLevel.HEADING_2
          : d.HeadingLevel.HEADING_3;
      out.push(new d.Paragraph({ heading: level, children: [new d.TextRun({ text: h[2] })] }));
      continue;
    }
    const bullet = /^[-*]\s+(.*)$/.exec(line);
    if (bullet) {
      out.push(
        new d.Paragraph({
          children: [new d.TextRun({ text: bullet[1] })],
          bullet: { level: 0 },
        }),
      );
      continue;
    }
    const numbered = /^(\d+)[.)]\s+(.*)$/.exec(line);
    if (numbered) {
      out.push(
        new d.Paragraph({ children: [new d.TextRun({ text: `${numbered[1]}. ${numbered[2]}` })] }),
      );
      continue;
    }
    out.push(new d.Paragraph({ children: [new d.TextRun({ text: line })] }));
  }
  return out;
}

export async function buildBriefDocx(draft: BriefDraft): Promise<File> {
  const d = await import('docx');
  const title = draft.title.trim() || 'Project brief';

  const children: Array<
    InstanceType<DocxNs['Paragraph']> | InstanceType<DocxNs['Table']>
  > = [
    new d.Paragraph({ heading: d.HeadingLevel.TITLE, children: [new d.TextRun({ text: title })] }),
    ...bodyParagraphs(d, draft.body),
  ];

  const shots = draft.screenshots.filter((s) => s.dataUrl);
  if (shots.length) {
    children.push(
      new d.Paragraph({
        heading: d.HeadingLevel.HEADING_2,
        children: [new d.TextRun({ text: 'Screens & flows' })],
        spacing: { before: 240 },
      }),
    );
    shots.forEach((s, i) => {
      const captionText = s.caption.trim() || `Screenshot ${i + 1}`;
      children.push(
        new d.Paragraph({
          spacing: { before: 160 },
          children: [
            new d.TextRun({ text: `Figure ${i + 1} — `, bold: true }),
            new d.TextRun({ text: captionText, bold: true }),
          ],
        }),
      );
      const width = Math.min(IMAGE_MAX_WIDTH, s.width || IMAGE_MAX_WIDTH);
      const scale = s.width ? width / s.width : 1;
      const height = Math.max(1, Math.round((s.height || width) * scale));
      children.push(
        new d.Paragraph({
          children: [
            new d.ImageRun({
              type: 'png',
              data: dataUrlToBytes(s.dataUrl),
              transformation: { width, height },
            }),
          ],
        }),
      );
    });
  }

  const doc = new d.Document({
    creator: 'GroundedIQ',
    title,
    sections: [{ properties: {}, children }],
  });
  const blob = await d.Packer.toBlob(doc);
  return new File([blob], `${safeStem(title)}.docx`, { type: DOCX_MIME });
}
