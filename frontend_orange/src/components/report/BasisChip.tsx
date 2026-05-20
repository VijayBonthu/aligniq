import { useState, useRef, useEffect } from 'react';
import type { BasisEvidence } from '../../types/report';
import EvidencePopover from './EvidencePopover';

interface Props {
  basisId: string;
  evidence?: BasisEvidence;
}

const KIND_LABEL: Record<string, string> = {
  document_quote: 'doc',
  retrieved_url: 'web',
  model_knowledge: 'model',
  inferred: 'inferred',
};

export default function BasisChip({ basisId, evidence }: Props) {
  const [open, setOpen] = useState(false);
  const anchorRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDocClick = (e: MouseEvent) => {
      if (anchorRef.current && !anchorRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, [open]);

  const kind = evidence?.basis ?? 'inferred';
  const kindLabel = KIND_LABEL[kind] ?? 'inferred';

  return (
    <span style={{ position: 'relative', display: 'inline-block' }}>
      <button
        ref={anchorRef}
        type="button"
        className={`basis-chip basis-chip--${kind}`}
        onClick={() => setOpen((v) => !v)}
        title={`${basisId} · ${kindLabel}`}
      >
        <span className="basis-chip__id">{basisId}</span>
        <span className="basis-chip__kind">{kindLabel}</span>
      </button>
      {open ? (
        <EvidencePopover basisId={basisId} evidence={evidence} onClose={() => setOpen(false)} />
      ) : null}
    </span>
  );
}
