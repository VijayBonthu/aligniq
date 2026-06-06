import React, { createContext, useState, useContext, useEffect, useCallback, ReactNode } from 'react';
import api from '../services/api';
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
  iat: number;
  exp: number;
}

interface AuthContextType {
  isAuthenticated: boolean;
  // False until the on-mount session check (decode + silent refresh) has resolved.
  // Public pages gate their "already signed in → /projects" redirect on this so a
  // dead session doesn't bounce /login → /projects → 401 → /login.
  authReady: boolean;
  user: UserData | null;
  subscription: SubscriptionData | null;
  login: (accessToken: string, refreshToken?: string) => Promise<boolean>;
  logout: () => void;
  refreshSubscription: () => Promise<void>;
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
  limitHit: null,
  showLimitHit: () => {},
  clearLimitHit: () => {},
};

const AuthContext = createContext<AuthContextType>(defaultValue);

export const useAuth = () => useContext(AuthContext);

export const AuthProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(() => {
    const token =
      localStorage.getItem('access_token') ||
      localStorage.getItem('regular_token') ||
      localStorage.getItem('google_auth_token');
    return !!token;
  });
  const [user, setUser] = useState<UserData | null>(null);
  const [subscription, setSubscription] = useState<SubscriptionData | null>(null);
  const [limitHit, setLimitHit] = useState<LimitHitDetail | null>(null);
  const [authReady, setAuthReady] = useState(false);

  const showLimitHit = useCallback((detail: LimitHitDetail) => setLimitHit(detail), []);
  const clearLimitHit = useCallback(() => setLimitHit(null), []);

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

  const login = async (accessToken: string, refreshToken?: string): Promise<boolean> => {
    try {
      localStorage.removeItem('regular_token');
      localStorage.removeItem('google_auth_token');
      localStorage.removeItem('access_token');

      localStorage.setItem('access_token', accessToken);
      localStorage.setItem('regular_token', accessToken);

      if (refreshToken) {
        localStorage.setItem('refresh_token', refreshToken);
      }

      api.defaults.headers.common['Authorization'] = `Bearer ${accessToken}`;

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

  useEffect(() => {
    const init = async () => {
      const token =
        localStorage.getItem('access_token') ||
        localStorage.getItem('regular_token') ||
        localStorage.getItem('google_auth_token');

      if (!token) {
        setAuthReady(true);
        return;
      }

      try {
        const userData = await decodeAndStoreUserData(token);
        const expMs = userData?.exp ? userData.exp * 1000 : 0;
        if (userData && expMs > Date.now()) {
          // Access token still valid — good to go.
          getSubscription().then(setSubscription).catch(() => {});
        } else {
          // Access token is missing/expired (they're short-lived). Try ONE silent
          // refresh so a returning user with a live refresh token stays signed in,
          // and a truly dead session resolves to logged-out instead of a 401 loop.
          const refreshToken = localStorage.getItem('refresh_token');
          if (!refreshToken) throw new Error('no refresh token');
          const { data } = await api.post('/auth/refresh', { refresh_token: refreshToken });
          localStorage.setItem('access_token', data.access_token);
          localStorage.setItem('refresh_token', data.refresh_token);
          localStorage.setItem('regular_token', data.access_token);
          api.defaults.headers.common['Authorization'] = `Bearer ${data.access_token}`;
          const refreshed = await decodeAndStoreUserData(data.access_token);
          if (!refreshed) throw new Error('decode after refresh failed');
          getSubscription().then(setSubscription).catch(() => {});
        }
      } catch {
        // Dead session — clear everything so public pages don't redirect into a loop.
        ['access_token', 'refresh_token', 'regular_token', 'google_auth_token',
         'user_id', 'user_email', 'user_provider'].forEach(k => localStorage.removeItem(k));
        delete api.defaults.headers.common['Authorization'];
        setUser(null);
        setIsAuthenticated(false);
      } finally {
        setAuthReady(true);
      }
    };
    init();
  }, []);

  const logout = () => {
    const refreshToken = localStorage.getItem('refresh_token');

    ['access_token', 'refresh_token', 'regular_token', 'google_auth_token',
     'user_id', 'user_email', 'user_provider'].forEach(k => localStorage.removeItem(k));

    delete api.defaults.headers.common['Authorization'];
    setIsAuthenticated(false);
    setUser(null);
    setSubscription(null);

    if (refreshToken) {
      api.post('/auth/logout', { refresh_token: refreshToken }).catch(() => {});
    }
  };

  return (
    <AuthContext.Provider value={{
      isAuthenticated, authReady, user, subscription, login, logout, refreshSubscription,
      limitHit, showLimitHit, clearLimitHit,
    }}>
      {children}
    </AuthContext.Provider>
  );
};

export default AuthContext;
