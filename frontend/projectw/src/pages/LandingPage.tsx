import { Link } from 'react-router-dom';
import { useDarkMode } from '../context/DarkModeContext';
import { useState, useEffect } from 'react';

const LandingPage = () => {
  const { darkMode, toggleDarkMode } = useDarkMode();
  const [theme, setTheme] = useState(true); // Default to dark theme
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  // Set up dark mode on component mount
  useEffect(() => {
    // Set dark mode by default
    if (theme) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  }, [theme]);

  // Toggle theme function
  const toggleTheme = () => {
    setTheme(!theme);
    localStorage.setItem('darkMode', (!theme).toString());
  };

  // Load saved theme preference when component mounts
  useEffect(() => {
    const savedTheme = localStorage.getItem('darkMode');
    if (savedTheme !== null) {
      setTheme(savedTheme === 'true');
    }
  }, []);

  return (
    <div className="min-h-screen relative overflow-hidden bg-gradient-to-br from-[#0f0c29] via-[#302b63] to-[#24243e] text-white">
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

      {/* Header with glass effect */}
      <header className="relative z-10 backdrop-blur-sm bg-black/10 border-b border-white/10">
        <div className="container mx-auto px-4 py-4 flex justify-between items-center">
          {/* Responsive logo with smaller size on mobile */}
          <div className="flex items-center">
            <div className="h-6 w-6 md:h-8 md:w-8 rounded-full bg-gradient-to-br from-blue-400 to-purple-600 flex items-center justify-center">
              <span className="text-sm md:text-base font-bold">AQ</span>
            </div>
            <h1 className="ml-1.5 md:ml-2 text-xs md:text-sm font-bold text-white">AlignIQ</h1>
          </div>
          
          {/* Desktop Navigation */}
          <div className="hidden md:flex items-center space-x-6">
            <nav className="flex items-center space-x-6">
              <a href="#features" className="px-3 py-2 text-gray-300 hover:text-white transition-colors rounded-md border border-transparent 
                hover:border-white/10 hover:bg-white/5 transform transition-all duration-200 hover:translate-y-[-2px] hover:shadow-lg hover:shadow-white/5">
                <span className="font-medium">Features</span>
              </a>
              <a href="#how-it-works" className="px-3 py-2 text-gray-300 hover:text-white transition-colors rounded-md border border-transparent 
                hover:border-white/10 hover:bg-white/5 transform transition-all duration-200 hover:translate-y-[-2px] hover:shadow-lg hover:shadow-white/5">
                <span className="font-medium">How It Works</span>
              </a>
              <a href="#pricing" className="px-3 py-2 text-gray-300 hover:text-white transition-colors rounded-md border border-transparent 
                hover:border-white/10 hover:bg-white/5 transform transition-all duration-200 hover:translate-y-[-2px] hover:shadow-lg hover:shadow-white/5">
                <span className="font-medium">Pricing</span>
              </a>
            </nav>
            
            {/* Theme toggle button */}
            <button 
              onClick={toggleTheme} 
              className="p-3 rounded-full bg-gradient-to-r from-blue-600/30 to-purple-600/30 hover:from-blue-500/40 hover:to-purple-500/40
                border border-purple-500/20 shadow-md transform transition-all duration-200 hover:translate-y-[-2px] hover:shadow-lg hover:shadow-purple-500/20"
              aria-label="Toggle theme"
            >
              {theme ? (
                <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
                </svg>
              ) : (
                <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
                </svg>
              )}
            </button>
            
            {/* Login/Signup buttons */}
            <div className="flex items-center space-x-3">
              <a 
                href="/login" 
                className="px-4 py-2 rounded-md border border-white/20 bg-white/5 backdrop-blur-sm 
                hover:bg-white/10 transition-all transform duration-200 hover:translate-y-[-2px] 
                hover:shadow-lg hover:shadow-white/10"
              >
                <span className="text-white font-semibold">Login</span>
              </a>
              <a 
                href="/register" 
                className="px-4 py-2 rounded-md bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-500 hover:to-purple-500
                shadow-md transform transition-all duration-200 hover:translate-y-[-2px] hover:shadow-lg hover:shadow-purple-500/30 border border-purple-500/30"
              >
                <span className="relative z-10 flex items-center justify-center text-white font-semibold">
                  Sign Up
                </span>
              </a>
            </div>
          </div>
          
          {/* Mobile Navigation */}
          <div className="flex items-center space-x-2 md:hidden">
            {/* Login button - compact for mobile */}
            <a 
              href="/login" 
              className="px-3 py-1.5 rounded-md border border-white/20 bg-white/5 text-sm"
            >
              Login
            </a>
            
            {/* Mobile Menu Button */}
            <button
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="p-2 rounded-md bg-white/5 border border-white/10"
            >
              {mobileMenuOpen ? (
                <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              ) : (
                <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
                </svg>
              )}
            </button>
          </div>
        </div>
        
        {/* Mobile Menu Dropdown */}
        {mobileMenuOpen && (
          <div className="md:hidden bg-black/20 backdrop-blur-md border-b border-white/10">
            <nav className="px-4 py-3 space-y-2">
              <a href="#features" className="block px-3 py-2 text-gray-300 hover:text-white hover:bg-white/5 rounded-md">
                Features
              </a>
              <a href="#how-it-works" className="block px-3 py-2 text-gray-300 hover:text-white hover:bg-white/5 rounded-md">
                How It Works
              </a>
              <a href="#pricing" className="block px-3 py-2 text-gray-300 hover:text-white hover:bg-white/5 rounded-md">
                Pricing
              </a>
            </nav>
          </div>
        )}
      </header>
      
      {/* Hero Section */}
      <section className="py-20 relative z-10">
        <div className="container mx-auto px-6 text-center">
          <div className="inline-block mb-4 px-6 py-2 rounded-full bg-white/5 backdrop-blur-sm border border-purple-500/20 text-purple-300">
            <span className="animate-pulse inline-block w-2 h-2 rounded-full bg-purple-400 mr-2"></span>
            AI-Powered Technology
          </div>
          <h1 className="text-5xl md:text-6xl font-bold mb-6 bg-clip-text text-transparent bg-gradient-to-r from-blue-300 via-purple-300 to-pink-300">
            Project Scoping That<br />Exceeds Expectations
          </h1>
          <p className="text-xl md:text-2xl text-gray-300 mb-10 max-w-3xl mx-auto">
            Transform your project requirements into detailed technical recommendations with our advanced AI tools.
          </p>
          <div className="flex flex-col sm:flex-row justify-center space-y-4 sm:space-y-0 sm:space-x-4">
            <a 
              href="/register" 
              className="px-8 py-4 rounded-md bg-gradient-to-r from-blue-600 to-purple-600 text-white font-medium 
              shadow-md transform transition-all duration-200 hover:translate-y-[-4px] hover:shadow-xl hover:shadow-purple-500/40 
              hover:from-blue-500 hover:to-purple-500 border border-purple-500/30 relative"
            >
              <span className="relative z-10 flex items-center justify-center text-white font-semibold">
                Get Started with AlignIQ
                <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 ml-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
                </svg>
              </span>
            </a>
            <a 
              href="#demo" 
              className="px-8 py-4 rounded-md bg-white/20 backdrop-blur-sm border border-white/20
              transform transition-all duration-200 hover:translate-y-[-4px] hover:bg-white/30 
              hover:shadow-lg hover:shadow-white/10"
            >
              <span className="text-white font-semibold">Watch Demo</span>
            </a>
          </div>
        </div>
      </section>
      
      {/* Feature Cards Section */}
      <section className="py-20 relative z-10">
        <div className="container mx-auto px-6">
          <div className="text-center mb-16">
            <h2 className="text-3xl md:text-4xl font-bold mb-4 bg-clip-text text-transparent bg-gradient-to-r from-blue-300 via-purple-300 to-pink-300">
              Eliminate Requirements Gaps
            </h2>
            <p className="text-xl text-gray-300 max-w-3xl mx-auto">
              Our AI platform ensures IT consulting firms and clients are always on the same page.
            </p>
          </div>
          
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {/* Card 1 - Requirements Analysis */}
            <div className="rounded-3xl backdrop-blur-sm bg-white/5 border border-white/10 p-8 hover:shadow-xl hover:shadow-purple-500/20 transition-all duration-300 group">
              <div className="h-16 w-16 rounded-2xl bg-gradient-to-br from-blue-500/20 to-blue-600/20 flex items-center justify-center mb-6 group-hover:rotate-3 transition-transform">
                <svg xmlns="http://www.w3.org/2000/svg" className="w-8 h-8 text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
              </div>
              <h3 className="text-2xl font-bold mb-3 group-hover:text-blue-300 transition-colors">Smart Document Analysis</h3>
              <p className="text-gray-300">Our AI engine analyzes your requirements documents and identifies gaps, ambiguities, and technical dependencies automatically.</p>
              
              <div className="mt-6 h-1 w-full bg-gradient-to-r from-blue-500/0 via-blue-500/50 to-blue-500/0 rounded-full overflow-hidden">
                <div className="h-full w-1/3 bg-blue-400 animate-pulse-slow transform transition-all group-hover:w-2/3 duration-700"></div>
              </div>
            </div>
            
            {/* Card 2 - Expert Questions */}
            <div className="rounded-3xl backdrop-blur-sm bg-white/5 border border-white/10 p-8 hover:shadow-xl hover:shadow-purple-500/20 transition-all duration-300 group">
              <div className="h-16 w-16 rounded-2xl bg-gradient-to-br from-purple-500/20 to-purple-600/20 flex items-center justify-center mb-6 group-hover:rotate-3 transition-transform">
                <svg xmlns="http://www.w3.org/2000/svg" className="w-8 h-8 text-purple-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
              <h3 className="text-2xl font-bold mb-3 group-hover:text-purple-300 transition-colors">Expert-Level Questions</h3>
              <p className="text-gray-300">Generate strategic questions that experienced consultants would ask, uncovering critical technical details clients might overlook.</p>
              
              <div className="mt-6 relative h-20">
                <div className="absolute inset-0 flex items-center justify-around opacity-50 group-hover:opacity-100 transition-opacity">
                  {[...Array(3)].map((_, i) => (
                    <div 
                      key={i} 
                      className="w-2 h-2 rounded-full bg-purple-400"
                      style={{ 
                        animationDuration: `${1.5 + i * 0.2}s`,
                        animationDelay: `${i * 0.2}s`,
                        animationIterationCount: 'infinite',
                        animationName: 'bounce-slow',
                        animationTimingFunction: 'ease-in-out'
                      }}
                    ></div>
                  ))}
                </div>
              </div>
            </div>
            
            {/* Card 3 - Project Acceleration */}
            <div className="rounded-3xl backdrop-blur-sm bg-white/5 border border-white/10 p-8 hover:shadow-xl hover:shadow-purple-500/20 transition-all duration-300 group">
              <div className="h-16 w-16 rounded-2xl bg-gradient-to-br from-pink-500/20 to-pink-600/20 flex items-center justify-center mb-6 group-hover:rotate-3 transition-transform">
                <svg xmlns="http://www.w3.org/2000/svg" className="w-8 h-8 text-pink-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
              </div>
              <h3 className="text-2xl font-bold mb-3 group-hover:text-pink-300 transition-colors">Accelerate Project Kickoffs</h3>
              <p className="text-gray-300">Reduce project start delays by 60% by eliminating lengthy requirement gathering cycles and misaligned expectations.</p>
              
              <div className="mt-6 flex justify-between items-center space-x-2">
                <div className="flex-1 h-2 bg-gray-700 rounded-full overflow-hidden">
                  <div className="h-full w-0 bg-pink-500 rounded-full group-hover:w-full transition-all duration-1000"></div>
                </div>
                <div className="text-pink-400 font-bold group-hover:scale-110 transition-transform">
                  <span className="inline-block group-hover:animate-ping">→</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* How It Works Section - New section */}
      <section className="py-20 relative z-10 border-t border-white/5">
        <div className="container mx-auto px-6">
          <div className="text-center mb-16">
            <h2 className="text-3xl md:text-4xl font-bold mb-4 bg-clip-text text-transparent bg-gradient-to-r from-blue-300 via-purple-300 to-pink-300">
              How AlignIQ Works
            </h2>
            <p className="text-xl text-gray-300 max-w-3xl mx-auto">
              Seamlessly bridging the gap between business needs and technical implementation.
            </p>
          </div>
          
          <div className="grid grid-cols-1 md:grid-cols-2 gap-12 items-center">
            <div className="order-2 md:order-1">
              <ol className="relative space-y-6">
                <li className="pl-8 relative">
                  <div className="absolute left-0 top-1 h-6 w-6 rounded-full bg-blue-500 flex items-center justify-center text-white text-sm font-bold">1</div>
                  <h3 className="text-xl font-bold mb-2 text-white">Upload Requirements</h3>
                  <p className="text-gray-300">Share your client's initial requirements document, RFP, or project brief with our AI system.</p>
                </li>
                
                <li className="pl-8 relative">
                  <div className="absolute left-0 top-1 h-6 w-6 rounded-full bg-purple-500 flex items-center justify-center text-white text-sm font-bold">2</div>
                  <h3 className="text-xl font-bold mb-2 text-white">AI-Powered Analysis</h3>
                  <p className="text-gray-300">Our system analyzes the document, identifies technical gaps, and generates expert-level clarification questions.</p>
                </li>
                
                <li className="pl-8 relative">
                  <div className="absolute left-0 top-1 h-6 w-6 rounded-full bg-pink-500 flex items-center justify-center text-white text-sm font-bold">3</div>
                  <h3 className="text-xl font-bold mb-2 text-white">Interactive Refinement</h3>
                  <p className="text-gray-300">Engage with the AI to further refine requirements, explore technical constraints, and uncover hidden assumptions.</p>
                </li>
                
                <li className="pl-8 relative">
                  <div className="absolute left-0 top-1 h-6 w-6 rounded-full bg-blue-500 flex items-center justify-center text-white text-sm font-bold">4</div>
                  <h3 className="text-xl font-bold mb-2 text-white">Comprehensive Documentation</h3>
                  <p className="text-gray-300">Receive a complete technical requirements document that aligns client expectations with implementation reality.</p>
                </li>
              </ol>
            </div>
            
            <div className="order-1 md:order-2 relative">
              <div className="absolute inset-0 bg-gradient-to-r from-blue-500/20 via-purple-500/20 to-pink-500/20 rounded-3xl filter blur-3xl opacity-30 animate-pulse-slow"></div>
              <div className="relative bg-gradient-to-br from-white/5 to-white/10 backdrop-blur-sm rounded-3xl border border-white/10 overflow-hidden p-6">
                <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-blue-500 via-purple-500 to-pink-500"></div>
                <div className="flex items-center space-x-2 mb-4">
                  <div className="w-3 h-3 rounded-full bg-red-500"></div>
                  <div className="w-3 h-3 rounded-full bg-yellow-500"></div>
                  <div className="w-3 h-3 rounded-full bg-green-500"></div>
                  <div className="ml-2 text-sm text-gray-400">AlignIQ Assistant</div>
                </div>
                
                <div className="rounded-lg bg-white/5 p-4 mb-4 border border-white/10">
                  <p className="text-gray-300 text-sm">Analyzing project requirements document...</p>
                  <div className="mt-2 h-1 w-full bg-gray-700 rounded-full overflow-hidden">
                    <div className="h-full bg-blue-500 rounded-full animate-progress"></div>
                  </div>
                </div>
                
                <div className="rounded-lg bg-purple-500/10 p-4 mb-4 border border-purple-500/20">
                  <p className="text-white text-sm font-medium mb-2">Issue: Unclear authentication requirements</p>
                  <p className="text-gray-300 text-sm">The document mentions "secure login" but doesn't specify requirements for:</p>
                  <ul className="list-disc list-inside text-gray-300 text-sm mt-1">
                    <li>Multi-factor authentication</li>
                    <li>Password policies</li>
                    <li>Session management</li>
                  </ul>
                </div>
                
                <div className="flex items-center">
                  <div className="flex-1 h-10 bg-white/5 rounded-lg border border-white/10 px-4 py-2 text-gray-400">
                    Ask a follow-up question...
                  </div>
                  <button className="ml-2 p-2 rounded-lg bg-gradient-to-r from-blue-600 to-purple-600 text-white">
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
                    </svg>
                  </button>
                </div>
                
                <div className="absolute bottom-0 left-0 w-full h-40 bg-gradient-to-t from-black/20 to-transparent pointer-events-none"></div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Update the CSS for animations */}
      <style jsx>{`
        @keyframes pulse {
          0%, 100% {
            opacity: 0.2;
          }
          50% {
            opacity: 0.8;
          }
        }
        
        .animate-spin-slow {
          animation: spin 8s linear infinite;
        }
        
        @keyframes spin {
          from {
            transform: rotate(0deg);
          }
          to {
            transform: rotate(360deg);
          }
        }
        
        .animate-pulse-slow {
          animation: pulse 3s ease-in-out infinite;
        }
        
        @keyframes bounce-slow {
          0%, 100% {
            transform: translateY(0);
          }
          50% {
            transform: translateY(-10px);
          }
        }
        
        @keyframes progress {
          0% {
            width: 0%;
          }
          50% {
            width: 70%;
          }
          100% {
            width: 100%;
          }
        }
        
        .animate-progress {
          animation: progress 3s ease-in-out infinite;
        }
      `}</style>
    </div>
  );
};

export default LandingPage;