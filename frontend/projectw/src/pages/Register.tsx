import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';

const Register = () => {
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const navigate = useNavigate();
  const { login } = useAuth();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (password !== confirmPassword) {
      setError('Passwords do not match');
      return;
    }

    setIsLoading(true);

    try {
      // Clear any existing tokens before registration
      localStorage.removeItem('token');
      localStorage.removeItem('regular_token');
      localStorage.removeItem('google_auth_token');
      
      const response = await axios.post(`${import.meta.env.VITE_API_URL}/registration`, {
        given_name: firstName,
        family_name: lastName,
        email,
        password,
      });

      if (response.data.access_token) {
        // Make sure to clear the auth header before setting the new one
        delete axios.defaults.headers.common['Authorization'];
        
        // Set the new token
        login(response.data.access_token);
        navigate('/dashboard');
      } else {
        setError('Registration successful. Please login.');
        navigate('/login');
      }
    } catch (error: any) {
      if (error.response && error.response.data) {
        setError(error.response.data.detail || 'Failed to register');
      } else {
        setError('Network error. Please try again.');
      }
    } finally {
      setIsLoading(false);
    }
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

      {/* Registration form */}
      <div className="relative z-10 w-full max-w-md p-8">
        <div className="backdrop-blur-sm bg-white/5 rounded-3xl border border-white/10 p-8 shadow-2xl">
          <div className="absolute inset-0 bg-gradient-to-r from-blue-500/5 via-purple-500/5 to-pink-500/5 rounded-3xl filter blur-xl opacity-30"></div>
          
          <div className="relative">
            <h2 className="text-3xl font-bold mb-6 text-center bg-clip-text text-transparent bg-gradient-to-r from-blue-300 via-purple-300 to-pink-300">
              Create Your Account
            </h2>
            
            <p className="text-gray-300 text-center mb-8">
              Join AlignIQ to streamline your technical requirements process
            </p>
            
            {error && (
              <div className="mb-6 p-3 bg-red-500/20 border border-red-500/30 rounded-md text-white">
                {error}
              </div>
            )}
            
            <form onSubmit={handleSubmit} className="space-y-5">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label htmlFor="firstName" className="block text-sm font-medium text-gray-300 mb-1">
                    First Name
                  </label>
                  <input
                    id="firstName"
                    type="text"
                    value={firstName}
                    onChange={(e) => setFirstName(e.target.value)}
                    required
                    className="w-full px-4 py-3 bg-white/5 border border-white/10 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-purple-500"
                    placeholder="John"
                  />
                </div>
                
                <div>
                  <label htmlFor="lastName" className="block text-sm font-medium text-gray-300 mb-1">
                    Last Name
                  </label>
                  <input
                    id="lastName"
                    type="text"
                    value={lastName}
                    onChange={(e) => setLastName(e.target.value)}
                    required
                    className="w-full px-4 py-3 bg-white/5 border border-white/10 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-purple-500"
                    placeholder="Doe"
                  />
                </div>
              </div>
              
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
                  className="w-full px-4 py-3 bg-white/5 border border-white/10 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-purple-500"
                  placeholder="you@example.com"
                />
              </div>
              
              <div>
                <label htmlFor="password" className="block text-sm font-medium text-gray-300 mb-1">
                  Password
                </label>
                <input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  className="w-full px-4 py-3 bg-white/5 border border-white/10 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-purple-500"
                  placeholder="••••••••"
                />
              </div>
              
              <div>
                <label htmlFor="confirmPassword" className="block text-sm font-medium text-gray-300 mb-1">
                  Confirm Password
                </label>
                <input
                  id="confirmPassword"
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  required
                  className="w-full px-4 py-3 bg-white/5 border border-white/10 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-purple-500"
                  placeholder="••••••••"
                />
              </div>
              
              <button
                type="submit"
                disabled={isLoading}
                className="w-full mt-2 py-3 px-4 rounded-lg bg-gradient-to-r from-blue-600 to-purple-600
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
                  {isLoading ? 'Creating Account...' : 'Create Account'}
                </span>
              </button>
              
              <div className="text-center mt-6">
                <p className="text-gray-300">
                  Already have an account?{' '}
                  <Link to="/login" className="text-purple-300 hover:underline font-medium">
                    Sign in
                  </Link>
                </p>
              </div>
            </form>
          </div>
        </div>
      </div>

      {/* Add CSS for animations */}
      <style jsx>{`
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

export default Register; 