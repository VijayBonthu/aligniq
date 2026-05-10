import { useState } from 'react';
import type { CustomSection, DeliverableSection } from '../../types/deliverable';

interface Props {
  anchorOptions: DeliverableSection[];
  onAdd: (custom: CustomSection) => void;
}

const PLACEHOLDER = `### Questions for Acme

- What is your expected peak QPS?
- Who owns the production runbook?
`;

export default function AddSectionButton({ anchorOptions, onAdd }: Props) {
  const [open, setOpen] = useState(false);
  const [markdown, setMarkdown] = useState(PLACEHOLDER);
  const [anchor, setAnchor] = useState(anchorOptions[0]?.id ?? '');

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        style={{
          margin: '12px',
          padding: '8px 14px',
          borderRadius: 8,
          border: '1px dashed var(--border-strong)',
          background: 'transparent',
          color: 'var(--accent)',
          fontFamily: 'var(--font-mono)',
          fontSize: 11,
          letterSpacing: '.08em',
          cursor: 'pointer',
        }}
      >
        + ADD CUSTOM SECTION
      </button>
    );
  }

  return (
    <div
      style={{
        margin: 12,
        padding: 12,
        borderRadius: 8,
        border: '1px solid var(--border-strong)',
        background: 'var(--surface-2)',
      }}
    >
      <label
        style={{
          fontSize: 10,
          fontFamily: 'var(--font-mono)',
          letterSpacing: '.08em',
          color: 'var(--fg-muted)',
          textTransform: 'uppercase',
        }}
      >
        Insert after
      </label>
      <select
        value={anchor}
        onChange={(e) => setAnchor(e.target.value)}
        style={{
          marginTop: 4,
          marginBottom: 10,
          width: '100%',
          fontSize: 12,
          fontFamily: 'var(--font-mono)',
          padding: '5px 8px',
          borderRadius: 6,
          border: '1px solid var(--border)',
          background: 'var(--surface)',
          color: 'var(--fg)',
        }}
      >
        {anchorOptions.map((s) => (
          <option key={s.id} value={s.id}>
            {s.heading_number} {s.heading_text}
          </option>
        ))}
      </select>
      <label
        style={{
          fontSize: 10,
          fontFamily: 'var(--font-mono)',
          letterSpacing: '.08em',
          color: 'var(--fg-muted)',
          textTransform: 'uppercase',
        }}
      >
        Markdown
      </label>
      <textarea
        value={markdown}
        onChange={(e) => setMarkdown(e.target.value)}
        rows={8}
        style={{
          marginTop: 4,
          width: '100%',
          fontFamily: 'var(--font-mono)',
          fontSize: 12,
          color: 'var(--fg)',
          background: 'var(--surface)',
          border: '1px solid var(--border)',
          borderRadius: 6,
          padding: 8,
          resize: 'vertical',
        }}
      />
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 8 }}>
        <button
          onClick={() => {
            setOpen(false);
            setMarkdown(PLACEHOLDER);
          }}
          style={btn()}
        >
          Cancel
        </button>
        <button
          onClick={() => {
            if (!anchor || !markdown.trim()) return;
            onAdd({
              id: `cs-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
              position: { after_section_id: anchor },
              markdown,
            });
            setOpen(false);
            setMarkdown(PLACEHOLDER);
          }}
          style={btn(true)}
        >
          Add
        </button>
      </div>
    </div>
  );
}

function btn(primary = false): React.CSSProperties {
  return {
    fontSize: 11,
    fontFamily: 'var(--font-mono)',
    letterSpacing: '.06em',
    padding: '5px 14px',
    borderRadius: 6,
    border: `1px solid ${primary ? 'var(--accent)' : 'var(--border)'}`,
    background: primary ? 'var(--accent-soft)' : 'transparent',
    color: primary ? 'var(--accent)' : 'var(--fg)',
    cursor: 'pointer',
  };
}
