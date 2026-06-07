import React, { useEffect, useRef } from 'react';

// Cloudflare Turnstile (free bot challenge) rendered via the vanilla script — no npm dep.
// If VITE_TURNSTILE_SITE_KEY is unset the widget renders nothing and the backend skips
// verification, so signup still works in local dev without keys.
const SITE_KEY = import.meta.env.VITE_TURNSTILE_SITE_KEY as string | undefined;
const SCRIPT_SRC = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';

declare global {
  interface Window {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    turnstile?: any;
  }
}

let scriptPromise: Promise<void> | null = null;
function loadTurnstileScript(): Promise<void> {
  if (window.turnstile) return Promise.resolve();
  if (scriptPromise) return scriptPromise;
  scriptPromise = new Promise<void>((resolve, reject) => {
    const s = document.createElement('script');
    s.src = SCRIPT_SRC;
    s.async = true;
    s.defer = true;
    s.onload = () => resolve();
    s.onerror = () => reject(new Error('Failed to load Turnstile'));
    document.head.appendChild(s);
  });
  return scriptPromise;
}

interface Props {
  onVerify: (token: string) => void;
  onExpire?: () => void;
}

export const TurnstileWidget: React.FC<Props> = ({ onVerify, onExpire }) => {
  const ref = useRef<HTMLDivElement>(null);
  const widgetId = useRef<string | null>(null);
  // Keep latest callbacks in a ref so the widget renders ONCE (parent re-renders on every
  // keystroke would otherwise re-mount it).
  const cb = useRef({ onVerify, onExpire });
  cb.current = { onVerify, onExpire };

  useEffect(() => {
    if (!SITE_KEY) return;
    let cancelled = false;
    loadTurnstileScript()
      .then(() => {
        if (cancelled || !ref.current || !window.turnstile) return;
        widgetId.current = window.turnstile.render(ref.current, {
          sitekey: SITE_KEY,
          callback: (token: string) => cb.current.onVerify(token),
          'expired-callback': () => cb.current.onExpire?.(),
          'error-callback': () => cb.current.onExpire?.(),
        });
      })
      .catch(() => {});
    return () => {
      cancelled = true;
      if (widgetId.current && window.turnstile) {
        try { window.turnstile.remove(widgetId.current); } catch { /* noop */ }
      }
    };
  }, []);

  if (!SITE_KEY) return null;
  return <div ref={ref} style={{ margin: '12px 0' }} />;
};
