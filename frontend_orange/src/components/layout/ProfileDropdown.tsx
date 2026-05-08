import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';

interface Props {
  onClose: () => void;
  initials: string;
  displayName: string;
  tierLabel: string;
}

export default function ProfileDropdown({ onClose, initials, displayName, tierLabel }: Props) {
  const { logout } = useAuth();
  const navigate = useNavigate();

  const handleSignOut = () => {
    onClose();
    logout();
    navigate('/login', { replace: true });
  };

  const items: Array<{ label: string; action?: () => void; danger?: boolean; divider?: boolean }> = [
    { label: 'Account settings', action: onClose },
    { label: 'Workspace', action: onClose },
    { label: 'Billing & plan', action: () => { onClose(); navigate('/pricing'); } },
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
              border: '1px solid rgba(255,138,101,.2)',
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
