import { useCallback, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

// The backend serves the OAuth callback page, so the postMessage we trust comes
// from the API origin (VITE_API_URL minus the /api/v1 suffix), NOT the frontend.
const API_BASE =
  (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/api\/v1\/?$/, '') ||
  'http://localhost:8080';

export type OAuthProvider = 'google' | 'github' | 'microsoft';

// Google keeps its original /auth/login endpoint; the newer providers are namespaced.
const LOGIN_PATH: Record<OAuthProvider, string> = {
  google: '/api/v1/auth/login',
  github: '/api/v1/auth/github/login',
  microsoft: '/api/v1/auth/microsoft/login',
};

/**
 * Shared "Sign in with X" popup flow for Google / GitHub / Microsoft.
 *
 *  - opens the backend login endpoint in a popup (the backend redirects to the
 *    provider and serves the callback page that postMessages the result back);
 *  - only trusts messages whose `event.origin` is the API origin;
 *  - the backend posts ONLY the access token (the refresh token is set as an
 *    httpOnly cookie on the callback response), which we hand to AuthContext.login;
 *  - surfaces pop-up-blocked, provider-reported errors, and closed-early cancels
 *    instead of hanging silently.
 *
 * NOTE: the backend posts with `targetOrigin = FRONTEND_URL`. Keep that env var in
 * sync with the origin actually serving the SPA, or the browser drops the message
 * and the user only ever sees the "cancelled" path here.
 *
 * Pass a stable `onError` (e.g. a useState setter) to receive failure messages.
 */
export function useOAuthPopup(provider: OAuthProvider, onError?: (msg: string) => void) {
  const { login } = useAuth();
  const navigate = useNavigate();
  const cleanupRef = useRef<(() => void) | null>(null);

  // Tear down any in-flight listener/interval if the component unmounts mid-flow.
  useEffect(() => () => cleanupRef.current?.(), []);

  return useCallback(() => {
    const popup = window.open(
      `${API_BASE}${LOGIN_PATH[provider]}`,
      `${provider}-auth`,
      'width=500,height=600,left=200,top=100',
    );
    if (!popup) {
      onError?.('Pop-up blocked. Please allow pop-ups for this site and try again.');
      return;
    }

    let settled = false;

    // Hoisted so `handler`/`interval` (declared below) and this can reference each
    // other; only ever invoked after both are initialized.
    function cleanup() {
      window.removeEventListener('message', handler);
      window.clearInterval(interval);
      cleanupRef.current = null;
    }

    const handler = async (event: MessageEvent) => {
      if (event.origin !== API_BASE) return; // only trust the API origin
      const data = event.data || {};
      if (data.type === `${provider}_auth_error`) {
        settled = true;
        cleanup();
        popup.close();
        onError?.(data.message || 'Sign-in failed. Please try again.');
        return;
      }
      if (data.type !== `${provider}_auth_success`) return;
      settled = true;
      cleanup();
      popup.close();
      const ok = await login(data.access_token);
      if (ok) navigate('/projects');
      else onError?.('Authentication failed. Please try again.');
    };

    const interval = window.setInterval(() => {
      if (popup.closed) {
        cleanup();
        if (!settled) onError?.('Sign-in was cancelled before it finished.');
      }
    }, 500);

    cleanupRef.current = cleanup;
    window.addEventListener('message', handler);
  }, [provider, login, navigate, onError]);
}
