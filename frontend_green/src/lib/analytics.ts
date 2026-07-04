// Cookieless web analytics — env-gated so it stays completely inert until configured
// (no script loaded, no network calls), and needs NO cookie-consent banner.
//
// To enable: set VITE_PLAUSIBLE_DOMAIN (e.g. "grounded-iq.com") in the build env.
// Plausible is cookieless and GDPR-friendly. If you standardise on PostHog instead,
// swap only the implementation below — the track() call sites stay unchanged.

const PLAUSIBLE_DOMAIN = import.meta.env.VITE_PLAUSIBLE_DOMAIN as string | undefined;
// tagged-events build also supports declarative class-based events; fine for plain use.
const PLAUSIBLE_SRC =
  (import.meta.env.VITE_PLAUSIBLE_SRC as string | undefined) ||
  'https://plausible.io/js/script.js';

declare global {
  interface Window {
    plausible?: (event: string, opts?: { props?: Record<string, unknown> }) => void;
  }
}

let started = false;

/** Load the analytics script once, only if a domain is configured. Safe to call always. */
export function initAnalytics() {
  if (started || !PLAUSIBLE_DOMAIN || typeof document === 'undefined') return;
  started = true;
  const s = document.createElement('script');
  s.defer = true;
  s.setAttribute('data-domain', PLAUSIBLE_DOMAIN);
  s.src = PLAUSIBLE_SRC;
  document.head.appendChild(s);
}

/**
 * Record a custom conversion event. No-ops when analytics is disabled or not yet
 * loaded, and never throws — analytics must never break a user flow.
 * (Pageviews are tracked automatically by the Plausible script, including SPA
 * route changes, so only meaningful conversions need explicit track() calls.)
 */
export function track(event: string, props?: Record<string, unknown>) {
  try {
    window.plausible?.(event, props ? { props } : undefined);
  } catch {
    /* ignore */
  }
}
