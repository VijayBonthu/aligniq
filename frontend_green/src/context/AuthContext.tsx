import React, { createContext, useState, useContext, useEffect, useCallback, useRef, ReactNode } from 'react';
import api, { setAccessToken, refreshAccessToken } from '../services/api';
import { getSubscription, SubscriptionData } from '../services/billingService';
import type { LimitHitDetail } from '../components/billing/UpgradeModal';

export type FirmRole = 'firm_admin' | 'member';

interface UserData {
  id: string;
  email: string;
  verified_email: boolean;
  provider: string;
  username?: string;
  role?: string;
  firm_id?: string;
  firm_role?: FirmRole;
  // Platform-admin (GroundedIQ staff) — gates the /admin ops console + maintenance bypass.
  is_staff?: boolean;
  iat: number;
  exp: number;
}

interface AuthContextType {
  isAuthenticated: boolean;
  // False until the on-mount session check (silent cookie refresh) has resolved.
  // Public pages gate their "already signed in → /projects" redirect on this, and
  // ProtectedRoute waits on it, so a hard reload doesn't bounce a live session to
  // /login before the refresh completes.
  authReady: boolean;
  user: UserData | null;
  subscription: SubscriptionData | null;
  // Only the access token — the refresh token is an httpOnly cookie set by the backend.
  login: (accessToken: string) => Promise<boolean>;
  logout: () => void;
  refreshSubscription: () => Promise<void>;
  // True if the user's effective tier unlocks `feature` (e.g. "version_compare", "jira").
  // Tier features are subscription-only — never purchasable with credits.
  hasFeature: (feature: string) => boolean;
  limitHit: LimitHitDetail | null;
  showLimitHit: (detail: LimitHitDetail) => void;
  clearLimitHit: () => void;
}

const defaultValue: AuthContextType = {
  isAuthenticated: false,
  authReady: false,
  user: null,
  subscription: null,
  login: async () => false,
  logout: () => {},
  refreshSubscription: async () => {},
  hasFeature: () => false,
  limitHit: null,
  showLimitHit: () => {},
  clearLimitHit: () => {},
};

const AuthContext = createContext<AuthContextType>(defaultValue);

export const useAuth = () => useContext(AuthContext);

export const AuthProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  // No synchronous token any more (it's in memory + httpOnly cookie), so we start
  // unauthenticated and resolve the real state in the on-mount effect below.
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false);
  const [user, setUser] = useState<UserData | null>(null);
  const [subscription, setSubscription] = useState<SubscriptionData | null>(null);
  const [limitHit, setLimitHit] = useState<LimitHitDetail | null>(null);
  const [authReady, setAuthReady] = useState(false);

  const showLimitHit = useCallback((detail: LimitHitDetail) => setLimitHit(detail), []);
  const clearLimitHit = useCallback(() => setLimitHit(null), []);
  const hasFeature = useCallback(
    (feature: string) => !!subscription?.limits?.features?.includes(feature),
    [subscription],
  );

  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent<LimitHitDetail>).detail;
      if (detail?.limit_type) setLimitHit(detail);
    };
    window.addEventListener('billing:limit-hit', handler);
    return () => window.removeEventListener('billing:limit-hit', handler);
  }, []);

  const refreshSubscription = async () => {
    try {
      const data = await getSubscription();
      setSubscription(data);
    } catch {
      // non-fatal
    }
  };

  const decodeAndStoreUserData = async (token: string) => {
    try {
      const response = await api.get(`/decode_token/${token}`);
      const userData: UserData = response.data;
      setUser(userData);
      setIsAuthenticated(true);
      localStorage.setItem('user_id', userData.id);
      localStorage.setItem('user_email', userData.email);
      localStorage.setItem('user_provider', userData.provider);
      return userData;
    } catch {
      setIsAuthenticated(false);
      return null;
    }
  };

  const login = async (accessToken: string): Promise<boolean> => {
    try {
      setAccessToken(accessToken);
      const userData = await decodeAndStoreUserData(accessToken);
      const success = !!userData;
      if (success) {
        getSubscription().then(setSubscription).catch(() => {});
      }
      return success;
    } catch {
      setIsAuthenticated(false);
      return false;
    }
  };

  const initRan = useRef(false);
  useEffect(() => {
    // Guard against React StrictMode's double-invoke (dev): two inits would fire two
    // concurrent refreshes. The shared single-flight refreshAccessToken() dedupes them,
    // and this ref makes init itself run exactly once.
    if (initRan.current) return;
    initRan.current = true;
    const init = async () => {
      try {
        // The access token lives in memory and is gone after a reload, so mint a fresh
        // one from the httpOnly refresh cookie. Success → signed in; failure (no/expired
        // cookie) → signed out, no redirect loop.
        const token = await refreshAccessToken();
        const userData = await decodeAndStoreUserData(token);
        if (!userData) throw new Error('decode after refresh failed');
        getSubscription().then(setSubscription).catch(() => {});
      } catch {
        setAccessToken(null);
        ['user_id', 'user_email', 'user_provider'].forEach(k => localStorage.removeItem(k));
        setUser(null);
        setIsAuthenticated(false);
      } finally {
        setAuthReady(true);
      }
    };
    init();
  }, []);

  const logout = () => {
    setAccessToken(null);
    ['user_id', 'user_email', 'user_provider'].forEach(k => localStorage.removeItem(k));
    setIsAuthenticated(false);
    setUser(null);
    setSubscription(null);
    // Server-side: revoke the refresh token + clear the httpOnly cookie (cookie sent
    // automatically). Fire-and-forget.
    api.post('/auth/logout').catch(() => {});
  };

  return (
    <AuthContext.Provider value={{
      isAuthenticated, authReady, user, subscription, login, logout, refreshSubscription,
      hasFeature, limitHit, showLimitHit, clearLimitHit,
    }}>
      {children}
    </AuthContext.Provider>
  );
};

export default AuthContext;
