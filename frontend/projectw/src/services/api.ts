import axios from 'axios';

// Create axios instance
const API_URL = import.meta.env.VITE_API_URL;
const api = axios.create({
  baseURL: API_URL,
  withCredentials: true,  // Important: needed to include cookies
});

// Function to get CSRF token from cookies
function getCsrfToken() {
  const match = document.cookie.match(new RegExp('(^| )csrf_token=([^;]+)'));
  return match ? match[2] : '';
}

// Debug function to check CSRF token
export function debugCsrf() {
  const cookie = getCsrfToken();
  console.log('CSRF Token in cookie:', cookie);
  console.log('All cookies:', document.cookie);
  return cookie;
}

// Add CSRF token to all state-changing requests
api.interceptors.request.use(config => {
  // Add CSRF token to headers for all non-GET requests
  if (config.method !== 'get') {
    const token = getCsrfToken();
    config.headers['X-CSRF-Token'] = token;
    
    // Log in development mode
    if (import.meta.env.DEV) {
      console.log(`Adding CSRF token to ${config.url}:`, token);
    }
  }
  
  // Add auth token if available
  const token = localStorage.getItem('token') || 
               localStorage.getItem('regular_token') || 
               localStorage.getItem('google_auth_token');
  
  if (token) {
    config.headers['Authorization'] = `Bearer ${token}`;
  }
  
  return config;
});

export default api; 