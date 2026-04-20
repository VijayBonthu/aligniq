import React, { createContext, useState, useContext, useEffect, ReactNode } from 'react';
import api from '../services/api';
import { getSubscription, SubscriptionData } from '../services/billingService';

interface UserData {
  id: string;
  email: string;
  verified_email: boolean;
  provider: string;
  username?: string;
  role?: string;
  iat: number;
  exp: number;
}

interface AuthContextType {
  isAuthenticated: boolean;
  user: UserData | null;
  subscription: SubscriptionData | null;
  login: (accessToken: string, refreshToken?: string) => Promise<boolean>;
  logout: () => void;
  refreshSubscription: () => Promise<void>;
}

const defaultValue: AuthContextType = {
  isAuthenticated: false,
  user: null,
  subscription: null,
  login: async () => false,
  logout: () => {},
  refreshSubscription: async () => {},
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
    const token =
      localStorage.getItem('access_token') ||
      localStorage.getItem('regular_token') ||
      localStorage.getItem('google_auth_token');

    if (token) {
      decodeAndStoreUserData(token).then(userData => {
        if (userData) getSubscription().then(setSubscription).catch(() => {});
      });
    }
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
    <AuthContext.Provider value={{ isAuthenticated, user, subscription, login, logout, refreshSubscription }}>
      {children}
    </AuthContext.Provider>
  );
};

export default AuthContext;
