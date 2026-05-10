import { useEffect, useRef, useState } from 'react';
import { loadMermaid } from '../../utils/mermaidLoader';
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
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    const renderId = `mmd-${id}`;
    loadMermaid()
      .then(async (mermaid) => {
        try {
          // Mermaid v10+ does NOT throw on syntax errors — it returns a rendered
          // "Syntax error in text" SVG. Pre-validate so we never inject that.
          const valid = await mermaid
            .parse(source, { suppressErrors: true })
            .catch(() => false);
          if (!valid) {
            if (!cancelled) setFailed(true);
            return;
          }
          const { svg: out } = await mermaid.render(renderId, source);
          if (out.includes('aria-roledescription="error"') || out.includes('Syntax error')) {
            if (!cancelled) setFailed(true);
            return;
          }
          if (!cancelled) setSvg(out);
        } catch {
          if (!cancelled) setFailed(true);
        } finally {
          // Mermaid leaves a temp measurement node on document.body. Strip it.
          const orphan = document.getElementById(`d${renderId}`);
          if (orphan && orphan.parentNode === document.body) orphan.remove();
        }
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [source, id]);

  if (failed) {
    return <AsciiBlock source={source} onZoom={onZoom} sourceLabel="diagram source" />;
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
