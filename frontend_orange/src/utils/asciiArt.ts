const ASCII_GLYPH_RE = /[─│┌┐└┘├┤┬┴┼╔╗╚╝║═╠╣╦╩╬▲▼◆●○]|[-+|]{3,}/;

/**
 * Heuristically wrap loose ASCII-art paragraphs in ```ascii fences so the
 * downstream segmenter can treat them uniformly. Skips content already
 * inside a fenced code block.
 */
export function wrapAsciiArt(md: string): string {
  const lines = md.split('\n');
  const out: string[] = [];
  let buf: string[] = [];
  let inFence = false;

  const flush = () => {
    if (buf.length === 0) return;
    const matchCount = buf.filter((l) => ASCII_GLYPH_RE.test(l)).length;
    if (matchCount >= 2 && matchCount / buf.length >= 0.4) {
      out.push('```ascii');
      out.push(...buf);
      out.push('```');
    } else {
      out.push(...buf);
    }
    buf = [];
  };

  for (const line of lines) {
    if (/^\s*```/.test(line)) {
      flush();
      out.push(line);
      inFence = !inFence;
      continue;
    }
    if (inFence) {
      out.push(line);
      continue;
    }
    if (line.trim() === '') {
      flush();
      out.push(line);
    } else {
      buf.push(line);
    }
  }
  flush();
  return out.join('\n');
}
