import React, { useState, useRef, useEffect } from 'react';

interface ProfileMenuProps {
  user: any | null;
  logout: () => void;
  sidebarExpanded: boolean;
}

const ProfileMenu: React.FC<ProfileMenuProps> = ({ user, logout, sidebarExpanded }) => {
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const [isMobile, setIsMobile] = useState(window.innerWidth < 768);
  
  // Detect mobile devices
  useEffect(() => {
    const handleResize = () => {
      setIsMobile(window.innerWidth < 768);
    };
    
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);
  
  // Close menu when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node) &&
          buttonRef.current && !buttonRef.current.contains(event.target as Node)) {
        setIsMenuOpen(false);
      }
    };
    
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);
  
  // Get initials for avatar
  const getInitials = (name: string) => {
    if (!name) return 'U';
    return name.split(' ').map(n => n[0]).join('').toUpperCase();
  };
  
  // Get user email from localStorage
  const userEmail = localStorage.getItem('user_email') || 'user@example.com';
  const userName = userEmail.split('@')[0];
  const userInitials = getInitials(userName);

  // Get position for the menu
  const getMenuPosition = () => {
    if (!buttonRef.current) return {};
    
    const buttonRect = buttonRef.current.getBoundingClientRect();
    
    if (isMobile) {
      return {
        width: "14rem", // Slightly smaller width for mobile
        bottom: window.innerHeight - buttonRect.top,
        left: Math.max(10, buttonRect.left),
      };
    } else if (sidebarExpanded) {
      // When sidebar is expanded - make width slightly smaller
      return {
        width: "14rem", // Slightly smaller than 16rem as requested
        left: buttonRect.left,
        bottom: window.innerHeight - buttonRect.top + 8,
      };
    } else {
      // When sidebar is collapsed - move higher up
      return {
        width: "14rem", // Consistent width but smaller
        left: "4rem", // Match collapsed sidebar width
        top: buttonRect.top - 260, // Move higher up as requested
      };
    }
  };
  
  return (
    <div className="relative" ref={menuRef}>
      <button 
        ref={buttonRef}
        onClick={() => setIsMenuOpen(!isMenuOpen)}
        className={`flex items-center transition-colors hover:bg-white/5
          ${sidebarExpanded ? 'w-full space-x-3 p-2 rounded-xl' : 'w-10 h-10 justify-center mx-auto rounded-full'}`}
        title={!sidebarExpanded ? "Account menu" : ""}
      >
        <div className="h-10 w-10 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center flex-shrink-0 shadow-lg">
          <span className="text-sm font-bold text-white">{userInitials}</span>
        </div>
        
        {sidebarExpanded && (
          <>
            <div className="flex-1 text-left truncate">
              <p className="text-sm font-medium text-gray-100">{userName}</p>
              <p className="text-xs text-gray-400 truncate">{userEmail}</p>
            </div>
            
            <svg 
              className={`w-5 h-5 text-gray-400 transform transition-transform duration-200 ${isMenuOpen ? 'rotate-180' : ''}`} 
              fill="none" 
              stroke="currentColor" 
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7"></path>
            </svg>
          </>
        )}
      </button>
      
      {isMenuOpen && (
        <div 
          className="fixed z-[9999] py-1 bg-gradient-to-b from-[#1c1c3b] to-[#1a1a36] rounded-lg shadow-xl border border-indigo-600/20 backdrop-blur-sm"
          style={getMenuPosition()}
        >
          <div className="px-4 py-3 border-b border-indigo-600/20">
            <p className="text-sm font-medium text-white">{userName}</p>
            <p className="text-xs text-indigo-300/80 truncate">{userEmail}</p>
          </div>
          
          <button className="w-full text-left px-4 py-2 text-sm hover:bg-white/5 flex items-center text-gray-200 transition-colors">
            <svg className="mr-2.5 h-4 w-4 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" 
                d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
            Settings
          </button>
          
          <button className="w-full text-left px-4 py-2 text-sm hover:bg-white/5 flex items-center text-gray-200 transition-colors">
            <svg className="mr-2.5 h-4 w-4 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
            </svg>
            Feedback
          </button>
          
          <button className="w-full text-left px-4 py-2 text-sm hover:bg-white/5 flex items-center text-gray-200 transition-colors">
            <svg className="mr-2.5 h-4 w-4 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            Help
          </button>
          
          <div className="border-t border-indigo-600/20 my-1"></div>
          
          <button 
            onClick={logout}
            className="w-full text-left px-4 py-2 text-sm hover:bg-white/5 flex items-center text-rose-400 transition-colors"
          >
            <svg className="mr-2.5 h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
            </svg>
            Logout
          </button>
        </div>
      )}
    </div>
  );
};

export default ProfileMenu; 