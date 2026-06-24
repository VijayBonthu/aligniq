import React, { useEffect, useState } from 'react';
import { useSiteConfig } from '../../context/SiteConfigContext';
import { getChangelog, ChangelogEntry } from '../../services/siteConfigService';

const SEEN_KEY = 'giq-changelog-seen';

function lastSeen(): string | null {
  try { return localStorage.getItem(SEEN_KEY); } catch { return null; }
}

const CATEGORY_COLOR: Record<string, string> = {
  feature: 'var(--accent, #34a37b)',
  improvement: 'var(--ok, #7ea889)',
  fix: 'var(--warn, #c89e6e)',
};

/** Bell button + "What's new" modal. Shows a dot when the latest published entry
 *  hasn't been seen on this device. Mount once (e.g. in AppShell). */
export default function WhatsNew() {
  const { config } = useSiteConfig();
  const [open, setOpen] = useState(false);
  const [entries, setEntries] = useState<ChangelogEntry[] | null>(null);
  const [seen, setSeen] = useState<string | null>(lastSeen);

  const latestId = config?.changelog_latest?.id || null;
  const hasUnseen = !!latestId && latestId !== seen;

  useEffect(() => {
    if (!open || entries) return;
    getChangelog().then(setEntries).catch(() => setEntries([]));
  }, [open, entries]);

  const onOpen = () => {
    setOpen(true);
    if (latestId) {
      try { localStorage.setItem(SEEN_KEY, latestId); } catch { /* ignore */ }
      setSeen(latestId);
    }
  };

  return (
    <>
      <button
        onClick={onOpen}
        title="What's new"
        style={{
          width: 40, height: 40, borderRadius: 8, border: 'none', background: 'transparent',
          color: 'var(--fg-muted)', display: 'flex', alignItems: 'center', justifyContent: 'center',
          position: 'relative', cursor: 'pointer',
        }}
      >
        <svg width="16" height="16" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
          <path d="M13.73 21a2 2 0 0 1-3.46 0" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        {hasUnseen && (
          <span style={{
            position: 'absolute', top: 7, right: 8, width: 8, height: 8, borderRadius: '50%',
            background: 'var(--accent, #34a37b)', border: '2px solid var(--surface, #1c1c25)',
          }} />
        )}
      </button>

      {open && (
        <div
          onClick={() => setOpen(false)}
          style={{
            position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 60,
            display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20,
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              width: 'min(560px, 100%)', maxHeight: '85dvh', overflow: 'auto',
              background: 'var(--surface, #1c1c25)', border: '1px solid var(--border-strong)',
              borderRadius: 'var(--radius-lg, 18px)', padding: 'clamp(18px, 5vw, 26px)',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 18 }}>
              <h2 style={{ fontFamily: 'var(--font-display, serif)', fontSize: 24, fontWeight: 500, margin: 0 }}>
                What's new
              </h2>
              <button
                onClick={() => setOpen(false)}
                aria-label="Close"
                style={{ background: 'none', border: 'none', color: 'var(--fg-muted)', fontSize: 22, cursor: 'pointer' }}
              >×</button>
            </div>

            {entries === null && <p style={{ color: 'var(--fg-dim)', fontSize: 14 }}>Loading…</p>}
            {entries?.length === 0 && <p style={{ color: 'var(--fg-dim)', fontSize: 14 }}>No updates yet.</p>}

            <div style={{ display: 'flex', flexDirection: 'column', gap: 22 }}>
              {entries?.map((e) => (
                <div key={e.id} style={{ borderLeft: '2px solid var(--border-strong)', paddingLeft: 16 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4, flexWrap: 'wrap' }}>
                    {e.version && (
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg-muted)' }}>{e.version}</span>
                    )}
                    {e.category && (
                      <span style={{
                        fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.08em', fontWeight: 600,
                        color: CATEGORY_COLOR[e.category] || 'var(--fg-muted)',
                      }}>{e.category}</span>
                    )}
                    {e.published_at && (
                      <span style={{ fontSize: 12, color: 'var(--fg-muted)', marginLeft: 'auto' }}>
                        {new Date(e.published_at).toLocaleDateString()}
                      </span>
                    )}
                  </div>
                  <div style={{ fontWeight: 600, fontSize: 15, marginBottom: 4 }}>{e.title}</div>
                  {e.body && (
                    <div style={{ color: 'var(--fg-dim)', fontSize: 13.5, lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>
                      {e.body}
                    </div>
                  )}
                  {e.media_url && /^https?:\/\//i.test(e.media_url) && (
                    <img
                      src={e.media_url} alt="" referrerPolicy="no-referrer"
                      onError={(ev) => { (ev.currentTarget as HTMLImageElement).style.display = 'none'; }}
                      style={{
                        display: 'block', marginTop: 10, maxWidth: '100%', maxHeight: 220,
                        borderRadius: 10, border: '1px solid var(--border-strong)',
                      }}
                    />
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
