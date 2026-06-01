import { useState } from 'react';
import type { DeliverableSection, PolishedSection } from '../../types/deliverable';
import SectionEditor from './SectionEditor';

interface Props {
  section: DeliverableSection;
  included: boolean;
  edited: string | null;
  polished: PolishedSection | null;
  polishing: boolean;
  onToggleInclude: (id: string, include: boolean) => void;
  onSaveEdit: (id: string, markdown: string) => void;
  onPolish: (id: string) => void;
  onRevertPolish: (id: string) => void;
}

const PIN = 'var(--accent)';
const ROW_BG = 'var(--surface)';

function row(level: number, included: boolean) {
  return {
    paddingLeft: level === 3 ? 30 : 12,
    paddingRight: 10,
    paddingTop: 8,
    paddingBottom: 8,
    borderBottom: '1px solid var(--border)',
    background: included ? ROW_BG : 'transparent',
    opacity: included ? 1 : 0.55,
  };
}

export default function SectionRow({
  section,
  included,
  edited,
  polished,
  polishing,
  onToggleInclude,
  onSaveEdit,
  onPolish,
  onRevertPolish,
}: Props) {
  const [expanded, setExpanded] = useState(false);
  const [editing, setEditing] = useState(false);
  const isInternal = section.kind === 'internal';
  const sourceMd = polished?.markdown ?? edited ?? section.raw_markdown;

  return (
    <div style={row(section.heading_level, included)}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <input
          type="checkbox"
          checked={included}
          onChange={(e) => onToggleInclude(section.id, e.target.checked)}
          style={{ accentColor: PIN, cursor: 'pointer' }}
        />
        <button
          onClick={() => setExpanded((v) => !v)}
          style={{
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            color: 'var(--fg-muted)',
            padding: 0,
            width: 14,
            display: 'flex',
            alignItems: 'center',
          }}
          title={expanded ? 'Collapse' : 'Expand'}
        >
          <svg
            width="10"
            height="10"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
            style={{ transform: expanded ? 'rotate(90deg)' : 'none', transition: 'transform .15s' }}
          >
            <polyline points="9 6 15 12 9 18" strokeWidth="2" strokeLinecap="round" />
          </svg>
        </button>
        <div style={{ flex: '1 1 130px', minWidth: 0 }}>
          <div
            style={{
              fontSize: section.heading_level === 2 ? 13.5 : 12.5,
              fontWeight: section.heading_level === 2 ? 600 : 500,
              color: 'var(--fg)',
              fontFamily: 'var(--font-sans)',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {section.heading_number ? `${section.heading_number} ` : ''}
            {section.heading_text}
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 4, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
          {isInternal && (
            <Pill
              label="INTERNAL"
              color="var(--warn)"
              title="This section is normally internal-only — defaults to excluded."
            />
          )}
          {polished && (
            <Pill
              label="POLISHED"
              color="var(--ok)"
              title={`Polished ${new Date(polished.polished_at).toLocaleString()}`}
            />
          )}
          {edited && !polished && (
            <Pill label="EDITED" color="var(--accent)" title="You edited this section." />
          )}
          <button
            onClick={() => setEditing((v) => !v)}
            disabled={!included}
            style={btnStyle(included)}
            title="Edit section markdown"
          >
            {editing ? 'Done' : 'Edit'}
          </button>
          <button
            onClick={() => onPolish(section.id)}
            disabled={!included || polishing}
            style={btnStyle(included && !polishing, polishing)}
            title="Run a single LLM Polish pass on this section"
          >
            {polishing ? 'Polishing…' : 'Polish'}
          </button>
          {polished && (
            <button
              onClick={() => onRevertPolish(section.id)}
              style={btnStyle(true)}
              title="Drop the polished override and use the source/edit markdown"
            >
              Revert
            </button>
          )}
        </div>
      </div>
      {expanded && !editing && (
        <pre
          style={{
            marginTop: 8,
            padding: 10,
            fontSize: 11.5,
            fontFamily: 'var(--font-mono)',
            color: 'var(--fg-muted)',
            background: 'var(--surface-2)',
            border: '1px solid var(--border)',
            borderRadius: 6,
            whiteSpace: 'pre-wrap',
            maxHeight: 240,
            overflow: 'auto',
          }}
        >
          {sourceMd}
        </pre>
      )}
      {editing && (
        <SectionEditor
          initial={edited ?? section.raw_markdown}
          onSave={(md) => {
            onSaveEdit(section.id, md);
            setEditing(false);
          }}
          onCancel={() => setEditing(false)}
        />
      )}
    </div>
  );
}

function btnStyle(enabled: boolean, busy = false): React.CSSProperties {
  return {
    fontSize: 11,
    fontFamily: 'var(--font-mono)',
    letterSpacing: '.06em',
    padding: '3px 8px',
    borderRadius: 6,
    border: '1px solid var(--border)',
    background: 'transparent',
    color: enabled ? 'var(--fg)' : 'var(--fg-muted)',
    cursor: enabled ? (busy ? 'progress' : 'pointer') : 'not-allowed',
    opacity: enabled ? 1 : 0.55,
  };
}

function Pill({ label, color, title }: { label: string; color: string; title?: string }) {
  return (
    <span
      title={title}
      style={{
        fontSize: 9,
        fontFamily: 'var(--font-mono)',
        letterSpacing: '.06em',
        padding: '2px 6px',
        borderRadius: 999,
        background: `color-mix(in oklab, ${color} 16%, transparent)`,
        color,
        border: `1px solid color-mix(in oklab, ${color} 30%, transparent)`,
      }}
    >
      {label}
    </span>
  );
}
