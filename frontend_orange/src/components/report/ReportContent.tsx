import { forwardRef, useMemo, useRef, useState } from 'react';
import { marked } from 'marked';
import DOMPurify from 'dompurify';
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

const FENCE_RE = /```(mermaid|ascii)\s*\n([\s\S]*?)```/g;

function segmentMarkdown(raw: string, instanceId: string): Segment[] {
  const prepared = wrapAsciiArt(raw);
  const segs: Segment[] = [];
  let lastIdx = 0;
  let counter = 0;
  let m: RegExpExecArray | null;
  FENCE_RE.lastIndex = 0;
  while ((m = FENCE_RE.exec(prepared)) !== null) {
    const before = prepared.slice(lastIdx, m.index);
    if (before.trim()) {
      const html = marked.parse(before, { async: false }) as string;
      segs.push({ kind: 'html', value: DOMPurify.sanitize(html), id: `${instanceId}-${counter++}` });
    }
    const lang = m[1] as 'mermaid' | 'ascii';
    segs.push({ kind: lang, value: m[2], id: `${instanceId}-${counter++}` });
    lastIdx = m.index + m[0].length;
  }
  const tail = prepared.slice(lastIdx);
  if (tail.trim()) {
    const html = marked.parse(tail, { async: false }) as string;
    segs.push({ kind: 'html', value: DOMPurify.sanitize(html), id: `${instanceId}-${counter++}` });
  }
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
