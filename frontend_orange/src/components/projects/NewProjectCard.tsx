import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

export default function NewProjectCard() {
  const navigate = useNavigate();
  const [hov, setHov] = useState(false);

  return (
    <button
      type="button"
      onClick={() => navigate('/new-project')}
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      style={{
        background: hov ? 'var(--surface-2)' : 'transparent',
        border: `1.5px dashed ${hov ? 'var(--accent)' : 'var(--border-strong)'}`,
        borderRadius: 'var(--radius-lg)',
        padding: '20px 22px',
        minHeight: 180,
        cursor: 'pointer',
        transition: 'all .18s ease',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 10,
        color: hov ? 'var(--accent)' : 'var(--fg-muted)',
      }}
    >
      <div
        style={{
          width: 36,
          height: 36,
          borderRadius: 9,
          background: hov ? 'var(--accent-soft)' : 'var(--surface)',
          border: `1px solid ${hov ? 'var(--accent)' : 'var(--border)'}`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          transition: 'all .18s',
        }}
      >
        <svg width="16" height="16" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path d="M12 5v14M5 12h14" strokeWidth="2.2" strokeLinecap="round" />
        </svg>
      </div>
      <div style={{ textAlign: 'center' }}>
        <p
          style={{
            fontFamily: 'var(--font-display)',
            fontSize: 15,
            color: hov ? 'var(--fg)' : 'var(--fg-dim)',
            margin: 0,
            letterSpacing: '-.01em',
          }}
        >
          New project
        </p>
        <p
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 9,
            letterSpacing: '.1em',
            textTransform: 'uppercase',
            color: 'var(--fg-muted)',
            margin: '4px 0 0',
          }}
        >
          Upload · Analyse
        </p>
      </div>
    </button>
  );
}
