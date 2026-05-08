import { useState, type ReactNode } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import ProfileDropdown from './ProfileDropdown';

type IconKey = 'grid' | 'msg' | 'chart' | 'settings';

const ICONS: Record<IconKey, ReactNode> = {
  grid: (
    <svg width="16" height="16" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <rect x="3" y="3" width="7" height="7" strokeWidth="1.8" rx="1" />
      <rect x="14" y="3" width="7" height="7" strokeWidth="1.8" rx="1" />
      <rect x="3" y="14" width="7" height="7" strokeWidth="1.8" rx="1" />
      <rect x="14" y="14" width="7" height="7" strokeWidth="1.8" rx="1" />
    </svg>
  ),
  msg: (
    <svg width="16" height="16" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" strokeWidth="1.8" />
    </svg>
  ),
  chart: (
    <svg width="16" height="16" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  settings: (
    <svg width="16" height="16" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <circle cx="12" cy="12" r="3" strokeWidth="1.8" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" strokeWidth="1.8" />
    </svg>
  ),
};

function NavIcon({
  icon, label, active, onClick,
}: { icon: IconKey; label: string; active: boolean; onClick: () => void }) {
  const [hov, setHov] = useState(false);
  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      title={label}
      style={{
        width: 40,
        height: 40,
        borderRadius: 8,
        border: 'none',
        background: active ? 'var(--accent-soft)' : hov ? 'var(--surface-2)' : 'transparent',
        color: active ? 'var(--accent)' : hov ? 'var(--fg)' : 'var(--fg-muted)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        transition: 'all .15s',
        position: 'relative',
        cursor: 'pointer',
      }}
    >
      {ICONS[icon]}
      {active && (
        <span
          style={{
            position: 'absolute',
            right: 2,
            top: '50%',
            transform: 'translateY(-50%)',
            width: 3,
            height: 16,
            background: 'var(--accent)',
            borderRadius: 2,
          }}
        />
      )}
    </button>
  );
}

export default function AppShell({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const { user, subscription } = useAuth();
  const [profileOpen, setProfileOpen] = useState(false);

  const activeView: 'dashboard' | 'messages' | 'reports' | 'settings' =
    pathname.startsWith('/messages') ? 'messages'
      : pathname.startsWith('/projects') || pathname.startsWith('/new-project') || pathname.startsWith('/chat') || pathname.startsWith('/dashboard') ? 'dashboard'
      : pathname.startsWith('/reports') ? 'reports'
      : pathname.startsWith('/settings') ? 'settings'
      : 'dashboard';

  const initials = (() => {
    const src = user?.username || user?.email || 'U';
    const parts = src.split(/[\s@._-]+/).filter(Boolean);
    if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
    return src.slice(0, 2).toUpperCase();
  })();

  const displayName = user?.username || user?.email || 'You';
  const tierLabel = subscription?.tier ? `${subscription.tier.toUpperCase()} PLAN` : 'FREE PLAN';

  return (
    <div style={{ display: 'flex', height: '100vh', background: 'var(--bg)', overflow: 'hidden' }}>
      <aside
        style={{
          width: 52,
          flexShrink: 0,
          borderRight: '1px solid var(--border)',
          background: 'var(--surface)',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          padding: '12px 0',
          gap: 2,
          position: 'relative',
          zIndex: 5,
        }}
      >
        <button
          onClick={() => navigate('/projects')}
          title="AlignIQ"
          style={{
            width: 30, height: 30, borderRadius: 7,
            background: 'var(--accent)',
            border: 'none',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 13, fontWeight: 800, color: '#1a0a04',
            fontFamily: 'var(--font-display)',
            cursor: 'pointer',
          }}
        >
          A
        </button>
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2, marginTop: 20 }}>
          <NavIcon icon="grid" label="Projects" active={activeView === 'dashboard'} onClick={() => navigate('/projects')} />
          <NavIcon icon="msg" label="Messages" active={activeView === 'messages'} onClick={() => navigate('/messages')} />
          <NavIcon icon="chart" label="Reports" active={activeView === 'reports'} onClick={() => navigate('/reports')} />
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2, paddingBottom: 4 }}>
          <NavIcon icon="settings" label="Settings" active={activeView === 'settings'} onClick={() => navigate('/settings')} />
          <button
            onClick={() => setProfileOpen(p => !p)}
            title="Profile"
            style={{
              width: 28, height: 28, borderRadius: '50%',
              background: profileOpen ? 'var(--accent)' : 'var(--accent-soft)',
              border: `1px solid ${profileOpen ? 'var(--accent)' : 'rgba(255,138,101,.2)'}`,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 10,
              color: profileOpen ? '#1a0a04' : 'var(--accent)',
              fontWeight: 600, fontFamily: 'var(--font-mono)',
              marginTop: 4, cursor: 'pointer', transition: 'all .15s',
            }}
          >
            {initials}
          </button>
        </div>
        {profileOpen && (
          <ProfileDropdown
            onClose={() => setProfileOpen(false)}
            initials={initials}
            displayName={displayName}
            tierLabel={tierLabel}
          />
        )}
      </aside>
      <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>{children}</div>
    </div>
  );
}
