import { forwardRef, useMemo, useRef, useState } from 'react';
import { marked } from 'marked';
import DOMPurify from 'dompurify';
import { wrapAsciiArt } from '../../utils/asciiArt';
import MermaidBlock from './MermaidBlock';
import AsciiBlock from './AsciiBlock';
import DiagramLightbox, { type LightboxContent } from './DiagramLightbox';
import type { EvidenceMap } from '../../types/report';

interface Props {
  content: string;
  variant?: 'report' | 'chat';
  evidenceMap?: EvidenceMap;
}

type Segment =
  | { kind: 'html'; value: string; id: string }
  | { kind: 'mermaid'; value: string; id: string }
  | { kind: 'ascii'; value: string; id: string };

const FENCE_RE = /```(mermaid|ascii)\s*\n([\s\S]*?)```/g;
const CITE_RE = /\[basis:([A-Za-z0-9_\-:.]+)\]/g;

function escapeAttr(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function safeHost(url: string): string {
  try {
    return new URL(url).host.replace(/^www\./, '');
  } catch {
    return 'source';
  }
}

function injectCitations(raw: string, evidenceMap?: EvidenceMap): string {
  return raw.replace(CITE_RE, (_m, id: string) => {
    const ev = evidenceMap?.[id];
    if (ev?.basis === 'retrieved_url' && ev.evidence) {
      const host = safeHost(ev.evidence);
      const title = ev.evidence_quote || ev.evidence;
      return ` <a class="src-cite src-cite--web" href="${escapeAttr(ev.evidence)}" target="_blank" rel="noreferrer noopener" title="${escapeAttr(title)}">${escapeAttr(host)}</a>`;
    }
    if (ev?.basis === 'document_quote') {
      const title = ev.evidence_quote || 'Grounded in the uploaded document';
      return ` <span class="src-cite src-cite--doc" title="${escapeAttr(title)}">doc</span>`;
    }
    if (ev?.basis === 'inferred' || id === 'inferred') {
      return ` <span class="src-cite src-cite--inferred" title="Inferred during report composition">inferred</span>`;
    }
    // model_knowledge or unknown id
    return ` <span class="src-cite src-cite--model" title="From the model&#39;s training knowledge — verify before relying on this claim">model</span>`;
  });
}

function segmentMarkdown(raw: string, instanceId: string, evidenceMap?: EvidenceMap): Segment[] {
  const prepared = injectCitations(wrapAsciiArt(raw), evidenceMap);
  const segs: Segment[] = [];
  let lastIdx = 0;
  let counter = 0;
  let m: RegExpExecArray | null;
  FENCE_RE.lastIndex = 0;
  while ((m = FENCE_RE.exec(prepared)) !== null) {
    const before = prepared.slice(lastIdx, m.index);
    if (before.trim()) {
      const html = marked.parse(before, { async: false }) as string;
      segs.push({
        kind: 'html',
        value: DOMPurify.sanitize(html, { ADD_ATTR: ['target', 'rel'] }),
        id: `${instanceId}-${counter++}`,
      });
    }
    const lang = m[1] as 'mermaid' | 'ascii';
    segs.push({ kind: lang, value: m[2], id: `${instanceId}-${counter++}` });
    lastIdx = m.index + m[0].length;
  }
  const tail = prepared.slice(lastIdx);
  if (tail.trim()) {
    const html = marked.parse(tail, { async: false }) as string;
    segs.push({
      kind: 'html',
      value: DOMPurify.sanitize(html, { ADD_ATTR: ['target', 'rel'] }),
      id: `${instanceId}-${counter++}`,
    });
  }
  return segs;
}

const ReportContent = forwardRef<HTMLDivElement, Props>(function ReportContent(
  { content, variant = 'report', evidenceMap },
  ref,
) {
  const idRef = useRef(`rc-${Math.random().toString(36).slice(2, 9)}`);
  const [lightbox, setLightbox] = useState<LightboxContent | null>(null);

  const segments = useMemo(
    () => segmentMarkdown(content, idRef.current, evidenceMap),
    [content, evidenceMap],
  );

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
