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
    loadMermaid()
      .then(async (mermaid) => {
        try {
          const { svg: out } = await mermaid.render(`mmd-${id}`, source);
          if (!cancelled) setSvg(out);
        } catch {
          if (!cancelled) setFailed(true);
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
