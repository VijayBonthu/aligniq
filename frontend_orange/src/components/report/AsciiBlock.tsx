import type { LightboxContent } from './DiagramLightbox';

interface Props {
  source: string;
  onZoom: (content: LightboxContent) => void;
  sourceLabel?: string;
}

export default function AsciiBlock({ source, onZoom, sourceLabel }: Props) {
  return (
    <figure className="diagram-block diagram-block--ascii">
      <div className="diagram-block__actions">
        {sourceLabel && <span className="diagram-block__tag">{sourceLabel}</span>}
        <button
          type="button"
          className="diagram-block__btn"
          onClick={() => onZoom({ kind: 'ascii', source, title: 'ASCII diagram' })}
        >
          Zoom
        </button>
      </div>
      <pre
        className="diagram-block__ascii"
        onClick={() => onZoom({ kind: 'ascii', source, title: 'ASCII diagram' })}
      >
        {source}
      </pre>
    </figure>
  );
}
