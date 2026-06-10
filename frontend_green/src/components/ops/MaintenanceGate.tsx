import React from 'react';
import { useSiteConfig } from '../../context/SiteConfigContext';
import { useAuth } from '../../context/AuthContext';
import { Logo } from '../Logo';

// Only render an embedded image for a real absolute http(s) URL (a stray/relative value
// must never become a broken or surprising request).
const isHttpUrl = (u?: string | null) => !!u && /^https?:\/\//i.test(u.trim());

const MaintenanceScreen: React.FC<{ title: string; message: string; eta: string; media?: string }> = ({ title, message, eta, media }) => (
  <div
    style={{
      minHeight: '100dvh', display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'var(--bg, #0d0d11)', color: 'var(--fg, #ece7dc)', textAlign: 'center',
      padding: 'clamp(16px, 5vw, 24px)', boxSizing: 'border-box',
    }}
  >
    <div style={{ width: '100%', maxWidth: 460 }}>
      <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 'clamp(20px, 5vw, 28px)' }}><Logo /></div>
      <div
        style={{
          display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 12, letterSpacing: '0.14em',
          textTransform: 'uppercase', color: 'var(--accent, #34a37b)', fontWeight: 600, marginBottom: 16,
        }}
      >
        <span style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--accent, #34a37b)' }} />
        Scheduled maintenance
      </div>
      {/* pre-wrap so a multiline title reads as written (e.g. a little "conversation");
          clamp() + break-word keeps it legible from phone to desktop. */}
      <h1 style={{ fontFamily: 'var(--font-display, Georgia, serif)', fontSize: 'clamp(26px, 6vw, 34px)', lineHeight: 1.12, margin: '0 0 14px', fontWeight: 500, whiteSpace: 'pre-wrap', overflowWrap: 'break-word' }}>
        {title || "We'll be right back"}
      </h1>
      <p style={{ color: 'var(--fg-dim, #a39d8e)', fontSize: 'clamp(14px, 3.6vw, 16px)', lineHeight: 1.65, margin: '0 0 18px', whiteSpace: 'pre-wrap', overflowWrap: 'break-word' }}>
        {message || 'GroundedIQ is down for brief maintenance. Your data is safe and we’ll be back shortly.'}
      </p>
      {isHttpUrl(media) && (
        <img
          src={media!.trim()} alt="" referrerPolicy="no-referrer"
          onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = 'none'; }}
          style={{
            display: 'block', margin: '0 auto 18px', maxWidth: 'min(320px, 100%)', maxHeight: 240,
            height: 'auto', borderRadius: 12, border: '1px solid var(--border, rgba(220,210,180,0.10))',
          }}
        />
      )}
      {eta && (
        <p style={{ color: 'var(--fg-muted, #6e6a5e)', fontSize: 13, fontFamily: 'var(--font-mono, monospace)', overflowWrap: 'break-word' }}>
          Expected back: {eta}
        </p>
      )}
    </div>
  </div>
);

const StaffBypassBar: React.FC = () => (
  <div
    style={{
      background: 'var(--warn, #c89e6e)', color: '#1a1205', fontSize: 12.5, fontWeight: 600,
      textAlign: 'center', padding: '6px 12px', letterSpacing: '0.02em',
    }}
  >
    Maintenance mode is ON — visitors see the maintenance page. You’re bypassing as staff.
  </div>
);

/**
 * Whole-app gate. When maintenance is on, the maintenance screen covers EVERY route —
 * no page (not even /login) is viewable — except for **staff**, who see the app with a
 * "maintenance is on" bar. Staff are identified by the DB-minted `is_staff` JWT claim,
 * recovered automatically on load from the httpOnly refresh cookie (AuthContext.init runs
 * regardless of this gate), so the admin who turned maintenance on keeps access; a fully
 * logged-out staffer recovers via the break-glass key (see PRODUCTION_RUNBOOK §9).
 *
 * `config.maintenance.on` is true either globally OR, for a *targeted* user, because the
 * authed /my-site-config overlay flipped it on just for them (SiteConfigContext) — so a
 * targeted user browses/​logs in normally and only hits this screen once identified.
 * Renders children before the first config load to avoid flashing the screen on a slow net.
 */
export default function MaintenanceGate({ children }: { children: React.ReactNode }) {
  const { config, ready } = useSiteConfig();
  const { user } = useAuth();

  const on = ready && !!config?.maintenance?.on;
  if (!on) return <>{children}</>;

  if (user?.is_staff) {
    return (
      <>
        <StaffBypassBar />
        {children}
      </>
    );
  }

  const m = config!.maintenance;
  return <MaintenanceScreen title={m.title} message={m.message} eta={m.eta} media={m.media_url} />;
}
