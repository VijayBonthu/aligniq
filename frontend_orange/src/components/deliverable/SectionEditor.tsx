import { useEffect, useRef, useState } from 'react';

interface Props {
  initial: string;
  onSave: (markdown: string) => void;
  onCancel: () => void;
}

export default function SectionEditor({ initial, onSave, onCancel }: Props) {
  const [value, setValue] = useState(initial);
  const ref = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    ref.current?.focus();
  }, []);

  return (
    <div style={{ marginTop: 8 }}>
      <textarea
        ref={ref}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        rows={Math.min(20, Math.max(6, value.split('\n').length))}
        spellCheck
        style={{
          width: '100%',
          fontFamily: 'var(--font-mono)',
          fontSize: 12,
          color: 'var(--fg)',
          background: 'var(--surface-2)',
          border: '1px solid var(--border-strong)',
          borderRadius: 6,
          padding: 10,
          resize: 'vertical',
          lineHeight: 1.5,
        }}
      />
      <div style={{ display: 'flex', gap: 8, marginTop: 6, justifyContent: 'flex-end' }}>
        <button onClick={onCancel} style={btn()}>Cancel</button>
        <button onClick={() => onSave(value)} style={btn(true)}>Save</button>
      </div>
    </div>
  );
}

function btn(primary = false): React.CSSProperties {
  return {
    fontSize: 11,
    fontFamily: 'var(--font-mono)',
    letterSpacing: '.06em',
    padding: '4px 12px',
    borderRadius: 6,
    border: `1px solid ${primary ? 'var(--accent)' : 'var(--border)'}`,
    background: primary ? 'var(--accent-soft)' : 'transparent',
    color: primary ? 'var(--accent)' : 'var(--fg)',
    cursor: 'pointer',
  };
}
