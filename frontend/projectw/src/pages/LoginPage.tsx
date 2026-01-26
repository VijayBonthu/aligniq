import React, { useState, useEffect } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import axios from 'axios';
import { useAuth } from '../context/AuthContext'; // Import useAuth from AuthContext

const API_URL = import.meta.env.VITE_API_URL;

const LoginPage: React.FC = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [checkingToken, setCheckingToken] = useState(true);
  const [hasNavigated, setHasNavigated] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const { isAuthenticated, login } = useAuth();

  console.log("LoginPage render state:", { 
    isAuthenticated, 
    hasNavigated, 
    checkingToken 
  });

  // Redirect if already authenticated
  useEffect(() => {
    console.log("Navigation effect running:", { 
      isAuthenticated, 
      hasNavigated 
    });
    
    if (isAuthenticated && !hasNavigated) {
      console.log("Attempting navigation to dashboard");
      setHasNavigated(true);
      navigate('/dashboard', { replace: true });
    }
  }, [isAuthenticated, hasNavigated, navigate]);

  // Check for existing token
  useEffect(() => {
    const checkExistingToken = async () => {
      console.log("checkExistingToken running:", { 
        isAuthenticated, 
        hasNavigated,
        token: localStorage.getItem('regular_token') // Add this to check token
      });

      if (isAuthenticated || hasNavigated) {
        console.log("Skipping token check - already authenticated or navigated");
        setCheckingToken(false);
        return;
      }

      try {
        const params = new URLSearchParams(location.search);
        const urlToken = params.get('token');
        
        if (urlToken) {
          console.log("Found URL token, attempting login");
          await login(urlToken);
          console.log("URL token login completed, isAuthenticated:", isAuthenticated);
          return;
        }

        const token = localStorage.getItem('token') || 
                     localStorage.getItem('regular_token') || 
                     localStorage.getItem('google_auth_token');
        
        if (token) {
          console.log("Found stored token, attempting login");
          await login(token);
          console.log("Stored token login completed, isAuthenticated:", isAuthenticated);
        }
      } catch (error) {
        console.error("Error during token verification:", error);
        localStorage.removeItem('token');
        localStorage.removeItem('regular_token');
        localStorage.removeItem('google_auth_token');
      } finally {
        setCheckingToken(false);
      }
    };

    checkExistingToken();
  }, [location.search, isAuthenticated, hasNavigated, login]);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setIsLoading(true);

    try {
      console.log("🔑 Attempting manual login");
      const response = await axios.post(`${API_URL}/login`, {
        email_address: email,
        password: password
      });

      const { access_token } = response.data;
      console.log("✅ Login API call successful, token:", access_token.substring(0, 10) + "...");
      
      const loginSuccess = await login(access_token);
      console.log("🔍 Login completed:", { loginSuccess, isAuthenticated });
      
      if (!loginSuccess) {
        throw new Error("Login failed");
      }
    } catch (err) {
      console.error("❌ Login error:", err);
      setError('Invalid email or password');
    } finally {
      setIsLoading(false);
    }
  };

  // If still checking token, show loading spinner
  if (checkingToken) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-[#0f0c29] via-[#302b63] to-[#24243e]">
        <div className="animate-spin h-12 w-12 border-4 border-white rounded-full border-t-transparent"></div>
      </div>
    );
  }

  const handleGoogleLogin = () => {
    // Open the Google auth in a popup window instead of redirecting
    const authWindow = window.open(
      `${API_URL}/auth/login`,
      'GoogleAuth',
      'width=800,height=600,left=200,top=100'
    );
    
    if (!authWindow) {
      setError('Popup blocked! Please allow popups for this site.');
      return;
    }
    
    // Set up listener to receive the token from the popup
    const handleAuthCallback = (event: MessageEvent) => {
      console.log("Received message:", event.data);
      
      // Check for the auth success message
      if (event.data && event.data.type === 'google_auth_success' && event.data.access_token) {
        console.log("Authentication successful, token received");
        
        // Get the token
        const token = event.data.access_token;
        
        // Store token in localStorage
        localStorage.setItem('google_auth_token', token);
        
        // Close the popup
        if (authWindow && !authWindow.closed) {
          authWindow.close();
        }
        
        // Navigate to dashboard
        navigate('/dashboard');
        
        // Remove the event listener
        window.removeEventListener('message', handleAuthCallback);
      }
    };
    
    // Add the message event listener
    window.addEventListener('message', handleAuthCallback);
    
    // Cleanup if window closes without completing auth
    const checkClosed = setInterval(() => {
      if (authWindow && authWindow.closed) {
        clearInterval(checkClosed);
        window.removeEventListener('message', handleAuthCallback);
      }
    }, 1000);
  };

  return (
    <div className="min-h-screen relative overflow-hidden bg-gradient-to-br from-[#0f0c29] via-[#302b63] to-[#24243e] text-white flex items-center justify-center">
      {/* Animated background lines */}
      <div className="absolute inset-0 opacity-20">
        <div className="absolute inset-0 flex">
          {[...Array(40)].map((_, i) => (
            <div 
              key={i}
              className="w-px bg-gradient-to-b from-transparent via-purple-400 to-transparent h-full mx-auto"
              style={{ 
                animationDuration: `${Math.random() * 2 + 2}s`,
                animationDelay: `${Math.random() * 2}s`,
                animationIterationCount: 'infinite',
                animationName: 'pulse',
                animationTimingFunction: 'ease-in-out'
              }}
            ></div>
          ))}
        </div>
      </div>

      {/* Header with AlignIQ logo */}
      <div className="absolute top-0 left-0 w-full">
        <header className="relative z-10 backdrop-blur-sm bg-black/10 border-b border-white/10">
          <div className="container mx-auto px-6 py-4">
            <Link to="/" className="flex items-center">
              <div className="h-10 w-10 rounded-full bg-gradient-to-br from-blue-400 to-purple-600 flex items-center justify-center">
                <span className="text-xl font-bold text-white">AQ</span>
              </div>
              <h1 className="ml-3 text-xl font-bold text-white">AlignIQ</h1>
            </Link>
          </div>
        </header>
      </div>

      {/* Login form */}
      <div className="relative z-10 w-full max-w-md p-8">
        <div className="backdrop-blur-sm bg-white/5 rounded-3xl border border-white/10 p-8 shadow-2xl">
          <div className="absolute inset-0 bg-gradient-to-r from-blue-500/5 via-purple-500/5 to-pink-500/5 rounded-3xl filter blur-xl opacity-30"></div>
          
          <div className="relative">
            <h2 className="text-3xl font-bold mb-8 text-center bg-clip-text text-transparent bg-gradient-to-r from-blue-300 via-purple-300 to-pink-300">
              Welcome Back
            </h2>
            
            {error && (
              <div className="mb-6 p-3 bg-red-500/20 border border-red-500/30 rounded-md text-white">
                {error}
              </div>
            )}
            
            <form onSubmit={handleLogin} className="space-y-6">
              <div>
                <label htmlFor="email" className="block text-sm font-medium text-gray-300 mb-1">
                  Email Address
                </label>
                <input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  autoComplete="username"
                  className="w-full px-4 py-3 bg-white/5 border border-white/10 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-purple-500"
                  placeholder="you@example.com"
                />
              </div>
              
              <div>
                <div className="flex items-center justify-between mb-1">
                  <label htmlFor="password" className="block text-sm font-medium text-gray-300">
                    Password
                  </label>
                  <Link to="/forgot-password" className="text-sm text-purple-300 hover:text-purple-200">
                    Forgot password?
                  </Link>
                </div>
                <input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  autoComplete="current-password"
                  className="w-full px-4 py-3 bg-white/5 border border-white/10 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-purple-500"
                  placeholder="••••••••"
                />
              </div>
              
              <button
                type="submit"
                disabled={isLoading}
                className="w-full py-3 px-4 rounded-lg bg-gradient-to-r from-blue-600 to-purple-600
                border border-purple-500/30 shadow-md transform transition-all duration-200 
                hover:translate-y-[-2px] hover:shadow-lg hover:shadow-purple-500/30 
                hover:from-blue-500 hover:to-purple-500 focus:outline-none"
              >
                <span className="relative z-10 flex items-center justify-center text-white font-semibold">
                  {isLoading ? (
                    <svg className="animate-spin h-5 w-5 mr-2" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none"></circle>
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                  ) : null}
                  {isLoading ? 'Signing In...' : 'Sign In'}
                </span>
              </button>
              
              {/* Google sign-in button with black metal finish */}
              <button 
                onClick={handleGoogleLogin}
                className="w-full flex items-center justify-center space-x-2 py-3 px-4 rounded-lg 
                  bg-gradient-to-b from-[#333333] to-[#121212] 
                  hover:from-[#444444] hover:to-[#222222]
                  border border-[#444444] shadow-lg
                  transform transition-all duration-200 hover:translate-y-[-2px] 
                  hover:shadow-xl text-white font-medium"
              >
                <svg width="20" height="20" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                  <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4" />
                  <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853" />
                  <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05" />
                  <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335" />
                </svg>
                <span>Sign in with Google</span>
              </button>
              
              <div className="text-center mt-6">
                <p className="text-gray-300">
                  Don't have an account?{' '}
                  <Link to="/register" className="text-purple-300 hover:underline font-medium">
                    Sign up
                  </Link>
                </p>
              </div>
            </form>
          </div>
        </div>
      </div>

      {/* Add CSS for animations */}
      <style>{`
        @keyframes pulse {
          0%, 100% {
            opacity: 0.2;
          }
          50% {
            opacity: 0.8;
          }
        }
      `}</style>
    </div>
  );
};

export default LoginPage;