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
  login: (token: string) => Promise<boolean>;
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
    // Initialize with token check
    const token = localStorage.getItem('regular_token') || 
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
      setIsAuthenticated(true); // Ensure we set authenticated here too
      
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

  const login = async (token: string): Promise<boolean> => {
    console.log("🔑 Login called with token:", token.substring(0, 10) + "...");
    
    try {
      localStorage.removeItem('regular_token');
      localStorage.removeItem('google_auth_token');
      localStorage.setItem('regular_token', token);
      
      axios.defaults.headers.common['Authorization'] = `Bearer ${token}`;
      
      const userData = await decodeAndStoreUserData(token);
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

  // Add initialization effect
  useEffect(() => {
    console.log("🏁 AuthProvider mounted");
    const token = localStorage.getItem('regular_token') || 
                 localStorage.getItem('google_auth_token');
    
    if (token) {
      console.log("🔄 Found token on mount, initializing auth");
      decodeAndStoreUserData(token);
    }
  }, []);

  // Debug effect for state changes
  useEffect(() => {
    console.log("🔄 Auth state changed:", { isAuthenticated, hasUser: !!user });
  }, [isAuthenticated, user]);

  const logout = () => {
    console.log("🚪 Logout called");
    localStorage.removeItem('regular_token');
    localStorage.removeItem('google_auth_token');
    localStorage.removeItem('user_id');
    localStorage.removeItem('user_email');
    localStorage.removeItem('user_provider');
    
    delete axios.defaults.headers.common['Authorization'];
    
    setIsAuthenticated(false);
    setUser(null);
    
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