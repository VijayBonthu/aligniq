import { useCallback, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

// The backend serves the OAuth callback page, so the postMessage we trust comes
// from the API origin (VITE_API_URL minus the /api/v1 suffix), NOT the frontend.
const API_BASE =
  (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/api\/v1\/?$/, '') ||
  'http://localhost:8080';

/**
 * Shared Google-OAuth popup flow for Login + Signup.
 *
 * Hardened over the old inline copies (which both pages duplicated verbatim):
 *  - rejects messages whose `event.origin` isn't the API origin (don't trust any
 *    page that can postMessage into the opener);
 *  - surfaces an error when the pop-up is blocked (`window.open` returns null);
 *  - surfaces an error when the user closes the pop-up before it completes,
 *    instead of hanging silently (the old code just cleared its listener).
 *
 * NOTE: the backend posts the result with `targetOrigin = FRONTEND_URL`. If that
 * env var doesn't match the origin actually serving the SPA, the browser drops
 * the message and the user only ever sees the "cancelled" path here — so keep
 * FRONTEND_URL in sync with the frontend origin (e.g. http://localhost:3002 in dev).
 *
 * Pass a stable `onError` (e.g. a useState setter) to receive failure messages.
 */
export function useGoogleAuth(onError?: (msg: string) => void) {
  const { login } = useAuth();
  const navigate = useNavigate();
  const cleanupRef = useRef<(() => void) | null>(null);

  // Tear down any in-flight listener/interval if the component unmounts mid-flow.
  useEffect(() => () => cleanupRef.current?.(), []);

  return useCallback(() => {
    const popup = window.open(
      `${API_BASE}/api/v1/auth/login`,
      'google-auth',
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
      if (event.data?.type !== 'google_auth_success') return;
      settled = true;
      cleanup();
      popup.close();
      const ok = await login(event.data.access_token, event.data.refresh_token);
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
  }, [login, navigate, onError]);
}
