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
  /** While true (message still streaming token-by-token), diagrams are shown as a
   *  placeholder instead of being rendered — a fenced block isn't closed yet, so
   *  rendering it mid-stream throws a mermaid parse error. Rendered once complete. */
  streaming?: boolean;
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
  { content, variant = 'report', streaming = false },
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
          // Mid-stream the fence isn't closed yet — defer the actual render so
          // mermaid doesn't choke on an incomplete diagram. Shows once complete.
          if (streaming) {
            return <DiagramPending key={seg.id} kind={seg.kind} />;
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

function DiagramPending({ kind }: { kind: 'mermaid' | 'ascii' }) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        margin: '10px 0',
        padding: '14px 16px',
        borderRadius: 10,
        border: '1px dashed var(--border-strong)',
        background: 'var(--surface-2)',
        color: 'var(--fg-muted)',
        fontFamily: 'var(--font-mono)',
        fontSize: 11,
        letterSpacing: '.04em',
      }}
    >
      <span
        style={{
          width: 11,
          height: 11,
          border: '2px solid var(--border-strong)',
          borderTopColor: 'var(--accent)',
          borderRadius: '50%',
          animation: 'spin 1s linear infinite',
        }}
      />
      Rendering {kind === 'ascii' ? 'ASCII diagram' : 'diagram'}…
    </div>
  );
}

export default ReportContent;
