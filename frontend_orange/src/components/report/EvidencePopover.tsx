import type { BasisEvidence } from '../../types/report';

interface Props {
  basisId: string;
  evidence?: BasisEvidence;
  onClose: () => void;
}

const KIND_DESC: Record<string, string> = {
  document_quote: 'Grounded in a quote from the uploaded document.',
  retrieved_url: 'Grounded in a web search result (Tavily).',
  model_knowledge: 'From the model\u2019s training knowledge. Verify before relying on it.',
  inferred: 'Synthesized during report composition without a specific upstream source.',
};

export default function EvidencePopover({ basisId, evidence, onClose }: Props) {
  const kind = evidence?.basis ?? 'inferred';
  const confidence = evidence?.confidence;

  return (
    <span
      role="dialog"
      className="basis-popover"
      onMouseDown={(e) => e.stopPropagation()}
    >
      <span className="basis-popover__header">
        <span className="basis-popover__id">{basisId}</span>
        <button type="button" className="basis-popover__close" onClick={onClose} aria-label="Close">
          ×
        </button>
      </span>
      <span className="basis-popover__row">
        <span className="basis-popover__label">Source</span>
        <span className={`basis-popover__kind basis-popover__kind--${kind}`}>{kind}</span>
      </span>
      {confidence ? (
        <span className="basis-popover__row">
          <span className="basis-popover__label">Confidence</span>
          <span>{confidence}</span>
        </span>
      ) : null}
      <span className="basis-popover__desc">{KIND_DESC[kind] ?? KIND_DESC.inferred}</span>
      {evidence?.evidence_quote ? (
        <blockquote className="basis-popover__quote">{evidence.evidence_quote}</blockquote>
      ) : null}
      {evidence?.basis === 'retrieved_url' && evidence.evidence ? (
        <a
          className="basis-popover__link"
          href={evidence.evidence}
          target="_blank"
          rel="noreferrer noopener"
        >
          {evidence.evidence}
        </a>
      ) : null}
      {evidence?.retrieved_at ? (
        <span className="basis-popover__meta">Retrieved {evidence.retrieved_at}</span>
      ) : null}
      {!evidence ? (
        <span className="basis-popover__meta">
          Detailed evidence not yet wired through for this report. The tag itself confirms the upstream agent emitted this id.
        </span>
      ) : null}
    </span>
  );
}
