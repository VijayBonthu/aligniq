import { useState } from 'react';
import type { CustomSection, DeliverableSection } from '../../types/deliverable';
import SectionEditor from './SectionEditor';

interface Props {
  custom: CustomSection;
  anchorOptions: DeliverableSection[];
  onChange: (next: CustomSection) => void;
  onDelete: (id: string) => void;
}

export default function CustomSectionRow({
  custom,
  anchorOptions,
  onChange,
  onDelete,
}: Props) {
  const [editing, setEditing] = useState(false);
  const heading = custom.markdown.split('\n').find((l) => l.trim().startsWith('#'))?.trim()
    ?? '(custom section)';
  const headingShort = heading.replace(/^#+\s*/, '');

  return (
    <div
      style={{
        paddingLeft: 12,
        paddingRight: 10,
        paddingTop: 8,
        paddingBottom: 8,
        borderBottom: '1px solid var(--border)',
        background: 'rgba(180, 140, 255, .06)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span
          style={{
            fontSize: 9,
            fontFamily: 'var(--font-mono)',
            letterSpacing: '.06em',
            padding: '2px 6px',
            borderRadius: 999,
            background: 'rgba(180,140,255,.15)',
            color: '#9d6cff',
            border: '1px solid rgba(180,140,255,.3)',
          }}
        >
          CUSTOM
        </span>
        <div
          style={{
            flex: 1,
            minWidth: 0,
            fontSize: 13,
            color: 'var(--fg)',
            fontFamily: 'var(--font-sans)',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {headingShort}
        </div>
        <select
          value={custom.position.after_section_id}
          onChange={(e) =>
            onChange({ ...custom, position: { after_section_id: e.target.value } })
          }
          style={{
            fontSize: 11,
            fontFamily: 'var(--font-mono)',
            padding: '3px 6px',
            borderRadius: 6,
            border: '1px solid var(--border)',
            background: 'var(--surface)',
            color: 'var(--fg)',
            maxWidth: 180,
          }}
          title="Insert after which section"
        >
          {anchorOptions.map((s) => (
            <option key={s.id} value={s.id}>
              after {s.heading_number} {s.heading_text}
            </option>
          ))}
        </select>
        <button onClick={() => setEditing((v) => !v)} style={btn()}>
          {editing ? 'Done' : 'Edit'}
        </button>
        <button onClick={() => onDelete(custom.id)} style={btn()} title="Delete custom section">
          Delete
        </button>
      </div>
      {editing && (
        <SectionEditor
          initial={custom.markdown}
          onSave={(md) => {
            onChange({ ...custom, markdown: md });
            setEditing(false);
          }}
          onCancel={() => setEditing(false)}
        />
      )}
    </div>
  );
}

function btn(): React.CSSProperties {
  return {
    fontSize: 11,
    fontFamily: 'var(--font-mono)',
    letterSpacing: '.06em',
    padding: '3px 8px',
    borderRadius: 6,
    border: '1px solid var(--border)',
    background: 'transparent',
    color: 'var(--fg)',
    cursor: 'pointer',
  };
}
