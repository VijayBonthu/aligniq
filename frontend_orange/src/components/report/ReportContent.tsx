import { forwardRef, useMemo, useRef, useState } from 'react';
import { marked, type Token } from 'marked';
import { sanitizeHtml, normalizeDiagramFences } from '../../utils/markdown';
import { wrapAsciiArt } from '../../utils/asciiArt';
import MermaidBlock from './MermaidBlock';
import AsciiBlock from './AsciiBlock';
import DiagramLightbox, { type LightboxContent } from './DiagramLightbox';

interface Props {
  content: string;
  variant?: 'report' | 'chat';
}

type Segment =
  | { kind: 'html'; value: string; id: string }
  | { kind: 'mermaid'; value: string; id: string }
  | { kind: 'ascii'; value: string; id: string };

/**
 * Split report markdown into renderable segments. Detection is delegated to
 * marked's own block lexer (the same path exportDocx uses) rather than a
 * hand-rolled fence regex, so every real-world fence variant — CRLF endings,
 * info strings after the tag, indented or `~~~` fences — is recognized. A
 * ```mermaid / ```ascii code token becomes its own diagram segment; all other
 * tokens are grouped and rendered to sanitized HTML. This guarantees a diagram
 * fence can never leak through as a raw code block.
 */
function segmentMarkdown(raw: string, instanceId: string): Segment[] {
  const tokens = marked.lexer(wrapAsciiArt(normalizeDiagramFences(raw)));
  const segs: Segment[] = [];
  let counter = 0;
  let htmlGroup: Token[] = [];

  const flushHtml = () => {
    if (htmlGroup.length === 0) return;
    // marked.parser resolves the link-definition map off the token list, so
    // carry it over to the sliced group to keep reference-style links working.
    (htmlGroup as unknown as { links: typeof tokens.links }).links = tokens.links;
    const html = marked.parser(htmlGroup) as string;
    if (html.trim()) {
      segs.push({ kind: 'html', value: sanitizeHtml(html), id: `${instanceId}-${counter++}` });
    }
    htmlGroup = [];
  };

  for (const tok of tokens) {
    // marked keeps the whole info string in `lang` (e.g. "mermaid title=x"),
    // so key off its first word.
    const lang = tok.type === 'code' ? (tok.lang ?? '').trim().split(/\s+/)[0] : '';
    if (tok.type === 'code' && (lang === 'mermaid' || lang === 'ascii')) {
      flushHtml();
      segs.push({ kind: lang, value: tok.text, id: `${instanceId}-${counter++}` });
    } else {
      htmlGroup.push(tok);
    }
  }
  flushHtml();
  return segs;
}

const ReportContent = forwardRef<HTMLDivElement, Props>(function ReportContent(
  { content, variant = 'report' },
  ref,
) {
  const idRef = useRef(`rc-${Math.random().toString(36).slice(2, 9)}`);
  const [lightbox, setLightbox] = useState<LightboxContent | null>(null);

  const segments = useMemo(() => segmentMarkdown(content, idRef.current), [content]);

  const className = variant === 'report' ? 'report-markdown' : 'chat-markdown';

  return (
    <>
      <div ref={ref} className={className}>
        {segments.map((seg) => {
          if (seg.kind === 'html') {
            return <div key={seg.id} dangerouslySetInnerHTML={{ __html: seg.value }} />;
          }
          if (seg.kind === 'mermaid') {
            return (
              <MermaidBlock key={seg.id} id={seg.id} source={seg.value} onZoom={setLightbox} />
            );
          }
          return <AsciiBlock key={seg.id} source={seg.value} onZoom={setLightbox} />;
        })}
      </div>
      <DiagramLightbox content={lightbox} onClose={() => setLightbox(null)} />
    </>
  );
});

export default ReportContent;
