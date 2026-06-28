import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';

interface Props {
  onClose: () => void;
  onHelp: () => void;
  initials: string;
  displayName: string;
  tierLabel: string;
}

export default function ProfileDropdown({ onClose, onHelp, initials, displayName, tierLabel }: Props) {
  const { logout, subscription } = useAuth();
  const navigate = useNavigate();
  const credits = subscription?.credits?.balance ?? 0;

  const handleSignOut = () => {
    onClose();
    logout();
    navigate('/login', { replace: true });
  };

  const items: Array<{ label: string; action?: () => void; danger?: boolean; divider?: boolean }> = [
    { label: 'Account settings', action: onClose },
    { label: 'Workspace', action: onClose },
    { label: 'Billing & plan', action: () => { onClose(); navigate('/pricing'); } },
    { label: 'Help & support', action: () => { onClose(); onHelp(); } },
    { label: '', divider: true },
    { label: 'Sign out', action: handleSignOut, danger: true },
  ];

  return (
    <>
      <div onClick={onClose} style={{ position: 'fixed', inset: 0, zIndex: 98 }} />
      <div
        style={{
          position: 'absolute',
          bottom: 8,
          left: 58,
          zIndex: 99,
          width: 210,
          background: 'var(--surface)',
          border: '1px solid var(--border-strong)',
          borderRadius: 10,
          boxShadow: 'var(--shadow-lg)',
          overflow: 'hidden',
          animation: 'fadeUp .15s ease',
        }}
      >
        <div style={{ padding: '11px 13px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 9 }}>
          <div
            style={{
              width: 28, height: 28, borderRadius: '50%',
              background: 'var(--accent-soft)',
              border: '1px solid rgba(52,163,123,.2)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 10, color: 'var(--accent)', fontWeight: 600,
              fontFamily: 'var(--font-mono)', flexShrink: 0,
            }}
          >
            {initials}
          </div>
          <div style={{ minWidth: 0 }}>
            <p style={{ fontSize: 12.5, fontWeight: 500, color: 'var(--fg)', margin: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{displayName}</p>
            <p style={{ fontFamily: 'var(--font-mono)', fontSize: 8, color: 'var(--fg-muted)', margin: 0, letterSpacing: '.06em', textTransform: 'uppercase' }}>{tierLabel}</p>
          </div>
        </div>
        {/* Credit balance — prepaid top-up wallet (ChatGPT/Claude-style). */}
        <button
          onClick={() => { onClose(); navigate('/pricing'); }}
          style={{
            width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            gap: 8, padding: '9px 13px', borderBottom: '1px solid var(--border)',
            background: 'var(--accent-soft)', border: 'none', cursor: 'pointer', textAlign: 'left',
          }}
          title="Buy credits"
        >
          <span style={{ display: 'flex', alignItems: 'center', gap: 7, minWidth: 0 }}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="2" aria-hidden>
              <circle cx="12" cy="12" r="9" />
              <path d="M12 7v10M9.5 9.2a2.6 2.6 0 0 1 2.5-1.6c1.5 0 2.5.9 2.5 2s-1 1.7-2.5 1.9-2.5.8-2.5 2 1 2 2.5 2a2.6 2.6 0 0 0 2.5-1.6" strokeLinecap="round" />
            </svg>
            <span style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--fg)' }}>
              {credits.toLocaleString()} <span style={{ fontWeight: 400, color: 'var(--fg-dim)' }}>credits</span>
            </span>
          </span>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--accent)', letterSpacing: '.06em', textTransform: 'uppercase' }}>Buy →</span>
        </button>
        {items.map((item, i) =>
          item.divider ? (
            <div key={i} style={{ height: 1, background: 'var(--border)', margin: '3px 0' }} />
          ) : (
            <button
              key={i}
              onClick={item.action}
              style={{
                width: '100%', display: 'flex', alignItems: 'center', padding: '8px 13px',
                background: 'none', border: 'none',
                color: item.danger ? 'var(--danger)' : 'var(--fg-dim)',
                fontSize: 12.5, cursor: 'pointer', textAlign: 'left', transition: 'all .12s',
                fontFamily: 'var(--font-sans)',
              }}
              onMouseEnter={e => {
                e.currentTarget.style.background = 'var(--surface-2)';
                e.currentTarget.style.color = item.danger ? 'var(--danger)' : 'var(--fg)';
              }}
              onMouseLeave={e => {
                e.currentTarget.style.background = 'transparent';
                e.currentTarget.style.color = item.danger ? 'var(--danger)' : 'var(--fg-dim)';
              }}
            >
              {item.label}
            </button>
          ),
        )}
      </div>
    </>
  );
}
