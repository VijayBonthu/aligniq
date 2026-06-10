import React, { useState } from 'react';
import { useSiteConfig } from '../../context/SiteConfigContext';
import { useAuth } from '../../context/AuthContext';
import type { AnnouncementKind } from '../../services/siteConfigService';

// A left accent stripe per kind keeps the banner legible in both themes (vs tinted
// backgrounds that can wash out). Colours map to the design tokens.
const KIND_COLOR: Record<AnnouncementKind, string> = {
  info: 'var(--accent, #34a37b)',
  success: 'var(--ok, #7ea889)',
  warning: 'var(--warn, #c89e6e)',
  maintenance: 'var(--warn, #c89e6e)',
  outage: 'var(--danger, #c87171)',
};

const DISMISS_KEY = 'giq-dismissed-announcements';

function readDismissed(): string[] {
  try { return JSON.parse(localStorage.getItem(DISMISS_KEY) || '[]'); } catch { return []; }
}
function persistDismissed(ids: string[]) {
  try { localStorage.setItem(DISMISS_KEY, JSON.stringify(ids.slice(-100))); } catch { /* ignore */ }
}

// Only treat a link as a real outbound link when it's an absolute http(s) URL.
// Anything else (blank, relative, stray text) must NOT navigate — a relative href
// would hit the SPA catch-all route and bounce the user to the landing page.
function externalHref(url?: string | null): string | null {
  const u = (url || '').trim();
  return /^https?:\/\//i.test(u) ? u : null;
}

const barStyle = (color: string): React.CSSProperties => ({
  display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap',
  background: 'var(--surface, #1c1c25)', color: 'var(--fg, #ece7dc)',
  borderBottom: '1px solid var(--border, rgba(220,210,180,0.10))',
  borderLeft: `3px solid ${color}`,
  padding: '9px 16px', fontSize: 13.5, lineHeight: 1.4,
});

export default function AnnouncementBar() {
  const { config } = useSiteConfig();
  const { isAuthenticated } = useAuth();
  const [hidden, setHidden] = useState<string[]>(readDismissed);

  if (!config) return null;

  const readOnly = config.read_only?.on ? config.read_only : null;
  const items = config.announcements.filter(
    (a) =>
      // 'users'-targeted notices only ever reach the client via the authed
      // /my-site-config (already matched to this user server-side), so show them as-is.
      (a.audience === 'all' || (a.audience === 'authenticated' && isAuthenticated) || a.audience === 'users') &&
      !hidden.includes(a.id),
  );
  if (!readOnly && !items.length) return null;

  const dismiss = (id: string) => {
    const next = [...hidden, id];
    setHidden(next);
    persistDismissed(next);
  };

  return (
    <div>
      {/* Read-only mode — a live state, so it's non-dismissible and always reflects the message. */}
      {readOnly && (
        <div role="status" style={barStyle(KIND_COLOR.warning)}>
          <span style={{ flex: 1, minWidth: '60%', overflowWrap: 'break-word' }}>
            <strong>Read-only mode</strong>
            <span style={{ color: 'var(--fg-dim, #a39d8e)' }}>
              {' — '}{readOnly.message?.trim() || 'Changes are temporarily disabled while we perform maintenance.'}
            </span>
          </span>
        </div>
      )}

      {items.map((a) => {
        const color = KIND_COLOR[a.kind] || KIND_COLOR.info;
        const href = externalHref(a.link_url);
        return (
          <div key={a.id} role="status" style={barStyle(color)}>
            <span style={{ flex: 1, minWidth: '60%', overflowWrap: 'break-word' }}>
              <strong>{a.title}</strong>
              {a.body ? <span style={{ color: 'var(--fg-dim, #a39d8e)' }}> — {a.body}</span> : null}
            </span>
            {href && (
              <a href={href} target="_blank" rel="noopener noreferrer"
                 style={{ color, fontWeight: 600, whiteSpace: 'nowrap' }}>
                {a.link_label || 'Learn more'} →
              </a>
            )}
            {a.dismissible && (
              <button
                type="button"
                onClick={() => dismiss(a.id)}
                aria-label="Dismiss"
                style={{
                  background: 'none', border: 'none', color: 'var(--fg-muted, #6e6a5e)',
                  cursor: 'pointer', fontSize: 18, lineHeight: 1, padding: '0 2px',
                }}
              >
                ×
              </button>
            )}
          </div>
        );
      })}
    </div>
  );
}
