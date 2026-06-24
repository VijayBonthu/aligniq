import { useEffect, useRef, useState } from 'react';
import { loadMermaid, renderMermaid } from '../../utils/mermaidLoader';
import { repairMermaid } from '../../utils/markdown';
import AsciiBlock from './AsciiBlock';
import type { LightboxContent } from './DiagramLightbox';

interface Props {
  source: string;
  id: string;
  onZoom: (content: LightboxContent) => void;
}

export default function MermaidBlock({ source, id, onZoom }: Props) {
  const [svg, setSvg] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const [errMsg, setErrMsg] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    const renderId = `mmd-${id}`;
    // Ensure mermaid is initialized before we queue a render. renderMermaid
    // (in mermaidLoader) serializes all renders: mermaid.render is not safe to
    // run concurrently, and a report mounts every diagram at once.
    loadMermaid()
      .then(async () => {
        // We deliberately do NOT pre-validate with mermaid.parse(): in some
        // mermaid builds parse() can throw for reasons unrelated to the diagram
        // (lazy diagram-loader / init issues), which would silently drop EVERY
        // diagram. render() is the real path; if it throws we capture why.
        // Try the source as-is first, then a repaired copy (common LLM mistakes
        // like unquoted parens). A valid diagram is never rewritten.
        const repaired = repairMermaid(source);
        const candidates = repaired !== source ? [source, repaired] : [source];
        let lastErr: string | null = null;
        for (const candidate of candidates) {
          try {
            const out = await renderMermaid(renderId, candidate);
            if (out.includes('aria-roledescription="error"') || out.includes('Syntax error')) {
              lastErr = 'mermaid produced an error diagram (invalid syntax)';
              continue;
            }
            if (!cancelled) setSvg(out);
            return;
          } catch (e) {
            lastErr = e instanceof Error ? e.message : String(e);
          }
        }
        if (!cancelled) {
          console.error('[MermaidBlock] render failed:', lastErr, '\n--- source ---\n', source);
          setErrMsg(lastErr);
          setFailed(true);
        }
      })
      .catch((e) => {
        if (!cancelled) {
          const msg = e instanceof Error ? e.message : String(e);
          console.error('[MermaidBlock] mermaid failed to load:', e);
          setErrMsg(`mermaid failed to load: ${msg}`);
          setFailed(true);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [source, id]);

  if (failed) {
    return (
      <div data-diagram-id={id}>
        {errMsg && (
          <div
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 11,
              color: 'var(--warn, #d98c4a)',
              margin: '14px 0 -6px',
              letterSpacing: '.02em',
            }}
          >
            Diagram couldn’t render: {errMsg}
          </div>
        )}
        <AsciiBlock source={source} onZoom={onZoom} sourceLabel="diagram source" />
      </div>
    );
  }
  if (!svg) {
    return (
      <div className="diagram-block diagram-block--loading" data-diagram-id={id}>
        Rendering diagram…
      </div>
    );
  }
  return (
    <figure className="diagram-block" data-diagram-id={id}>
      <div className="diagram-block__actions">
        <button
          type="button"
          className="diagram-block__btn"
          onClick={() => onZoom({ kind: 'svg', svg, source, title: 'Mermaid diagram' })}
        >
          Zoom
        </button>
      </div>
      <div
        ref={containerRef}
        className="diagram-block__svg"
        onClick={() => onZoom({ kind: 'svg', svg, source, title: 'Mermaid diagram' })}
        dangerouslySetInnerHTML={{ __html: svg }}
      />
    </figure>
  );
}
