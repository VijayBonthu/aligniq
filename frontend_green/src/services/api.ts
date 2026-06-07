import axios from 'axios';

const API_URL = import.meta.env.VITE_API_URL;
const api = axios.create({
  baseURL: API_URL,
  withCredentials: true, // send/receive the httpOnly refresh cookie + CSRF cookie
});

// ---------------------------------------------------------------------------
// Access token: in browser MEMORY only (never localStorage). The long-lived
// refresh token lives in an httpOnly cookie the browser sends automatically on
// /auth/* calls, so JS can't read it (XSS can't exfiltrate the session). On a
// hard reload this module's variable is gone; AuthContext re-mints the access
// token on mount via refreshAccessToken() (cookie).
// ---------------------------------------------------------------------------
let accessToken: string | null = null;
export function setAccessToken(token: string | null) {
  accessToken = token;
}
export function getAccessToken(): string | null {
  return accessToken;
}

function getCsrfToken() {
  const match = document.cookie.match(new RegExp('(^| )csrf_token=([^;]+)'));
  return match ? match[2] : '';
}

api.interceptors.request.use(config => {
  if (config.method !== 'get') {
    config.headers['X-CSRF-Token'] = getCsrfToken();
  }
  if (accessToken) {
    config.headers['Authorization'] = `Bearer ${accessToken}`;
  }
  // Jira tokens live server-side (jira_credentials, keyed to the user). /jira/* calls
  // are authorized by the normal app bearer above — no Jira token in the browser.
  return config;
});

// ---------------------------------------------------------------------------
// Single-flight refresh: every caller (AuthContext on mount, and any 401/403 in
// the interceptor below) shares ONE in-flight POST /auth/refresh. This prevents
// concurrent refreshes — which, with React StrictMode's double-mount or multiple
// tabs, used to fire two refreshes at once and leave the app authenticated but
// token-less. The backend no longer rotates the refresh token, so this is safe.
// ---------------------------------------------------------------------------
let refreshPromise: Promise<string> | null = null;
export function refreshAccessToken(): Promise<string> {
  if (!refreshPromise) {
    refreshPromise = api
      .post('/auth/refresh')
      .then(({ data }) => {
        setAccessToken(data.access_token);
        return data.access_token as string;
      })
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

// Non-sensitive cached user fields (no tokens here anymore — those are memory/cookie).
function clearCachedUser() {
  ['user_id', 'user_email', 'user_provider'].forEach(k => localStorage.removeItem(k));
}

// A request that reached a protected endpoint with NO/expired bearer. FastAPI's
// HTTPBearer returns 403 "Not authenticated" when the header is MISSING, and 401 when
// the token is present but invalid — we recover from both. The email-verification gate
// also returns 403, but its detail is an object ({code:"EMAIL_NOT_VERIFIED"}), so a
// string-equality check keeps us from looping on it.
function isMissingOrExpiredAuth(error: { response?: { status?: number; data?: { detail?: unknown } } }): boolean {
  const r = error.response;
  if (!r) return false;
  if (r.status === 401) return true;
  if (r.status === 403 && r.data?.detail === 'Not authenticated') return true;
  return false;
}

api.interceptors.response.use(
  response => response,
  async error => {
    const original = error.config;

    if (error.response?.status === 402) {
      const detail = error.response.data?.detail;
      if (detail && typeof detail === 'object' && detail.limit_type) {
        window.dispatchEvent(new CustomEvent('billing:limit-hit', { detail }));
      }
      return Promise.reject(error);
    }

    if (!isMissingOrExpiredAuth(error) || !original || original._retry) {
      return Promise.reject(error);
    }

    const url: string = original.url || '';
    // Don't run app-token refresh on the auth endpoints themselves (avoids loops).
    // /auth/jira/login is intentionally NOT excluded — it needs a valid app token, so a
    // 401 there should refresh-and-retry like any other protected call.
    if (
      url.includes('/auth/refresh') ||
      url.includes('/registration') ||
      (url.includes('/login') && !url.includes('/jira'))
    ) {
      return Promise.reject(error);
    }

    original._retry = true;
    try {
      const token = await refreshAccessToken();
      original.headers['Authorization'] = `Bearer ${token}`;
      return api(original);
    } catch (err) {
      setAccessToken(null);
      clearCachedUser();
      window.location.href = '/login';
      return Promise.reject(err);
    }
  }
);

export default api;
