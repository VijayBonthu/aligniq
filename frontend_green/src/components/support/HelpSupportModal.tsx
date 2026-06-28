import SupportForm from './SupportForm';

interface Props {
  open: boolean;
  onClose: () => void;
}

export default function HelpSupportModal({ open, onClose }: Props) {
  if (!open) return null;

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 1000,
        background: 'rgba(0,0,0,.6)',
        backdropFilter: 'blur(4px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 20,
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          width: '100%',
          maxWidth: 480,
          maxHeight: '90vh',
          overflowY: 'auto',
          background: 'var(--surface)',
          border: '1px solid var(--border-strong)',
          borderRadius: 'var(--radius-lg)',
          padding: 28,
          boxShadow: 'var(--shadow-lg)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12, marginBottom: 18 }}>
          <div>
            <p
              style={{
                fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '.14em',
                textTransform: 'uppercase', color: 'var(--accent)', margin: '0 0 8px',
              }}
            >
              Help &amp; support
            </p>
            <h2
              className="display"
              style={{ fontWeight: 400, letterSpacing: '-.02em', fontSize: 22, color: 'var(--fg)', margin: 0 }}
            >
              How can we help?
            </h2>
            <p style={{ fontSize: 13, color: 'var(--fg-dim)', margin: '6px 0 0', lineHeight: 1.5 }}>
              Report a bug or share feedback. We read every message and reply by email.
            </p>
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            style={{
              background: 'none', border: 'none', color: 'var(--fg-muted)', cursor: 'pointer',
              fontSize: 22, lineHeight: 1, padding: 2, flexShrink: 0,
            }}
          >
            ×
          </button>
        </div>
        <SupportForm onDone={onClose} />
      </div>
    </div>
  );
}
