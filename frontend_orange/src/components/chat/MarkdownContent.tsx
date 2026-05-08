import { useEffect, useMemo, useRef, useState } from 'react';
import { marked } from 'marked';
import DOMPurify from 'dompurify';

const MERMAID_FENCE = /```mermaid\s*\n([\s\S]*?)```/g;

interface Segment {
  kind: 'html' | 'mermaid';
  value: string;
  id: string;
}

let mermaidPromise: Promise<typeof import('mermaid').default> | null = null;

function loadMermaid() {
  if (!mermaidPromise) {
    mermaidPromise = import('mermaid').then((m) => {
      const mermaid = m.default;
      mermaid.initialize({
        startOnLoad: false,
        theme: 'dark',
        themeVariables: {
          background: 'transparent',
          primaryColor: '#1f1411',
          primaryBorderColor: '#3a2a23',
          primaryTextColor: '#f4ece6',
          lineColor: '#7a665b',
        },
      });
      return mermaid;
    });
  }
  return mermaidPromise;
}

function MermaidDiagram({ source, id }: { source: string; id: string }) {
  const [svg, setSvg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    loadMermaid()
      .then(async (mermaid) => {
        try {
          const { svg: out } = await mermaid.render(`mmd-${id}`, source);
          if (!cancelled) setSvg(out);
        } catch (err) {
          if (!cancelled) setError(err instanceof Error ? err.message : 'Diagram render failed');
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Mermaid failed to load');
      });
    return () => {
      cancelled = true;
    };
  }, [source, id]);

  if (error) {
    return (
      <pre
        style={{
          padding: 12,
          background: 'var(--surface-2)',
          border: '1px solid var(--border)',
          borderRadius: 8,
          fontSize: 12,
          color: 'var(--danger)',
          whiteSpace: 'pre-wrap',
          margin: '8px 0',
        }}
      >
        Mermaid render failed: {error}
      </pre>
    );
  }
  if (!svg) {
    return (
      <div
        style={{
          padding: 18,
          textAlign: 'center',
          color: 'var(--fg-muted)',
          fontSize: 12,
          background: 'var(--surface-2)',
          border: '1px solid var(--border)',
          borderRadius: 8,
          margin: '8px 0',
        }}
      >
        Rendering diagram…
      </div>
    );
  }
  return (
    <div
      style={{
        margin: '8px 0',
        padding: 12,
        background: 'var(--surface-2)',
        border: '1px solid var(--border)',
        borderRadius: 8,
        overflowX: 'auto',
      }}
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}

interface Props {
  content: string;
}

export default function MarkdownContent({ content }: Props) {
  const idRef = useRef(`md-${Math.random().toString(36).slice(2, 9)}`);

  const segments: Segment[] = useMemo(() => {
    const out: Segment[] = [];
    let lastIdx = 0;
    let match: RegExpExecArray | null;
    let counter = 0;
    MERMAID_FENCE.lastIndex = 0;
    while ((match = MERMAID_FENCE.exec(content)) !== null) {
      const before = content.slice(lastIdx, match.index);
      if (before.trim()) {
        const html = marked.parse(before, { async: false }) as string;
        out.push({ kind: 'html', value: DOMPurify.sanitize(html), id: `${idRef.current}-${counter++}` });
      }
      out.push({ kind: 'mermaid', value: match[1].trim(), id: `${idRef.current}-${counter++}` });
      lastIdx = match.index + match[0].length;
    }
    const tail = content.slice(lastIdx);
    if (tail.trim()) {
      const html = marked.parse(tail, { async: false }) as string;
      out.push({ kind: 'html', value: DOMPurify.sanitize(html), id: `${idRef.current}-${counter++}` });
    }
    return out;
  }, [content]);

  return (
    <div className="chat-markdown" style={{ fontSize: 13.5, lineHeight: 1.6 }}>
      {segments.map((seg) =>
        seg.kind === 'html' ? (
          <div key={seg.id} dangerouslySetInnerHTML={{ __html: seg.value }} />
        ) : (
          <MermaidDiagram key={seg.id} id={seg.id} source={seg.value} />
        ),
      )}
    </div>
  );
}
