import React, { createContext, useState, useContext, useEffect, ReactNode } from 'react';
import axios from 'axios';

const API_URL = import.meta.env.VITE_API_URL;

interface UserData {
  id: string;
  email: string;
  verified_email: boolean;
  provider: string;
  iat: number;
  exp: number;
}

interface AuthContextType {
  isAuthenticated: boolean;
  user: UserData | null;
  login: (accessToken: string, refreshToken?: string) => Promise<boolean>;
  logout: () => void;
}

const defaultValue: AuthContextType = {
  isAuthenticated: false,
  user: null,
  login: async () => false,
  logout: () => {}
};

const AuthContext = createContext<AuthContextType>(defaultValue);

export const useAuth = () => useContext(AuthContext);

interface AuthProviderProps {
  children: ReactNode;
}

export const AuthProvider: React.FC<AuthProviderProps> = ({ children }) => {
  console.log("🔄 AuthProvider rendering");
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(() => {
    const token = localStorage.getItem('access_token') ||
                 localStorage.getItem('regular_token') ||
                 localStorage.getItem('google_auth_token');
    console.log("🏁 Initial auth state check:", { hasToken: !!token });
    return !!token;
  });
  const [user, setUser] = useState<UserData | null>(null);

  const decodeAndStoreUserData = async (token: string) => {
    console.log("📞 decodeAndStoreUserData called with token:", token.substring(0, 10) + "...");
    try {
      const response = await axios.get(`${API_URL}/decode_token/${token}`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      console.log("✅ decode_token API call successful, response:", response.data);

      const userData: UserData = response.data;
      setUser(userData);
      setIsAuthenticated(true);

      localStorage.setItem('user_id', userData.id);
      localStorage.setItem('user_email', userData.email);
      localStorage.setItem('user_provider', userData.provider);

      return userData;
    } catch (error) {
      console.error("❌ Error in decodeAndStoreUserData:", error);
      setIsAuthenticated(false);
      return null;
    }
  };

  const login = async (accessToken: string, refreshToken?: string): Promise<boolean> => {
    console.log("🔑 Login called with token:", accessToken.substring(0, 10) + "...");

    try {
      localStorage.removeItem('regular_token');
      localStorage.removeItem('google_auth_token');
      localStorage.removeItem('access_token');

      localStorage.setItem('access_token', accessToken);
      localStorage.setItem('regular_token', accessToken);

      if (refreshToken) {
        localStorage.setItem('refresh_token', refreshToken);
      }

      axios.defaults.headers.common['Authorization'] = `Bearer ${accessToken}`;

      const userData = await decodeAndStoreUserData(accessToken);
      const success = !!userData;

      console.log("🔐 Login completed:", {
        success,
        isAuthenticated: success,
        hasUser: !!userData
      });

      return success;
    } catch (error) {
      console.error("❌ Error in login:", error);
      setIsAuthenticated(false);
      return false;
    }
  };

  useEffect(() => {
    console.log("🏁 AuthProvider mounted");
    const token = localStorage.getItem('access_token') ||
                 localStorage.getItem('regular_token') ||
                 localStorage.getItem('google_auth_token');

    if (token) {
      console.log("🔄 Found token on mount, initializing auth");
      decodeAndStoreUserData(token);
    }
  }, []);

  useEffect(() => {
    console.log("🔄 Auth state changed:", { isAuthenticated, hasUser: !!user });
  }, [isAuthenticated, user]);

  const logout = () => {
    console.log("🚪 Logout called");

    const refreshToken = localStorage.getItem('refresh_token');

    // Clear state immediately so navigation after logout works correctly
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('regular_token');
    localStorage.removeItem('google_auth_token');
    localStorage.removeItem('user_id');
    localStorage.removeItem('user_email');
    localStorage.removeItem('user_provider');
    delete axios.defaults.headers.common['Authorization'];
    setIsAuthenticated(false);
    setUser(null);

    // Best-effort revocation — fire and forget
    if (refreshToken) {
      axios.post(`${API_URL}/auth/logout`, { refresh_token: refreshToken }).catch(() => {});
    }

    console.log("✅ Logout complete");
  };

  const value = {
    isAuthenticated,
    user,
    login,
    logout
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
};

export default AuthContext;
