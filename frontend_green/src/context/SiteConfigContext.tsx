import React, { createContext, useContext, useEffect, useState, useCallback, useRef, ReactNode } from 'react';
import { getSiteConfig, getMySiteConfig, SiteConfig } from '../services/siteConfigService';
import { useAuth } from './AuthContext';

interface SiteConfigContextType {
  config: SiteConfig | null;
  ready: boolean;          // false until the first fetch resolves (avoid flashing maintenance)
  refresh: () => void;
}

const SiteConfigContext = createContext<SiteConfigContextType>({
  config: null,
  ready: false,
  refresh: () => {},
});

export const useSiteConfig = () => useContext(SiteConfigContext);

// Poll cadence for maintenance/announcement freshness. Kept short so changes reach
// users within seconds without a manual reload; combined with refetch-on-focus and
// refetch-on-login below, this is the standard "banner/flag" freshness pattern.
const POLL_MS = 20_000;

export const SiteConfigProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [config, setConfig] = useState<SiteConfig | null>(null);
  const [ready, setReady] = useState(false);
  const { isAuthenticated } = useAuth();
  // Tracked in a ref so `refresh` stays stable (no re-subscribe churn) but always reads
  // the current auth state when deciding whether to fetch targeted announcements.
  const authedRef = useRef(isAuthenticated);
  authedRef.current = isAuthenticated;

  const refresh = useCallback(async () => {
    try {
      const base = await getSiteConfig();
      if (authedRef.current) {
        // Per-user overlay from the authed endpoint, matched to this user server-side.
        // Best-effort: a failure here never blocks the public config.
        try {
          const mine = await getMySiteConfig();
          if (mine.announcements.length) {
            const seen = new Set(base.announcements.map((a) => a.id));
            base.announcements = [...base.announcements, ...mine.announcements.filter((a) => !seen.has(a.id))];
          }
          // Targeted ("troll") maintenance: this user sees the maintenance page even when
          // global maintenance is off. The MaintenanceGate keys off config.maintenance.on.
          if (mine.maintenance?.on) base.maintenance = mine.maintenance;
        } catch { /* ignore — per-user overlay is non-critical */ }
      }
      setConfig(base);
    } catch {
      // Backend unreachable: keep last-known config. A true origin outage is handled
      // at the Cloudflare edge, not here.
    } finally {
      setReady(true);
    }
  }, []);

  useEffect(() => {
    refresh();
    const interval = window.setInterval(refresh, POLL_MS);
    // Refetch the moment the user returns to the tab — makes new/updated/removed
    // announcements and lifted maintenance appear effectively instantly when active.
    const onFocus = () => refresh();
    const onVisible = () => { if (document.visibilityState === 'visible') refresh(); };
    // The api interceptor fires this on any 503 maintenance response.
    const onMaintenance = () => refresh();
    window.addEventListener('focus', onFocus);
    document.addEventListener('visibilitychange', onVisible);
    window.addEventListener('ops:maintenance', onMaintenance);
    return () => {
      window.clearInterval(interval);
      window.removeEventListener('focus', onFocus);
      document.removeEventListener('visibilitychange', onVisible);
      window.removeEventListener('ops:maintenance', onMaintenance);
    };
  }, [refresh]);

  // Re-fetch when auth changes (notably right after login) so a just-lifted
  // maintenance, new announcement, or new staff status is reflected immediately
  // instead of stranding the user on a stale maintenance screen. (Fixes "login →
  // maintenance page → snaps to projects ~10s later".)
  useEffect(() => { refresh(); }, [isAuthenticated, refresh]);

  return (
    <SiteConfigContext.Provider value={{ config, ready, refresh }}>
      {children}
    </SiteConfigContext.Provider>
  );
};

export default SiteConfigContext;
