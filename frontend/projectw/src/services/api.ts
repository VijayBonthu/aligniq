import axios from 'axios';

const API_URL = import.meta.env.VITE_API_URL;
const api = axios.create({
  baseURL: API_URL,
  withCredentials: true,
});

function getCsrfToken() {
  const match = document.cookie.match(new RegExp('(^| )csrf_token=([^;]+)'));
  return match ? match[2] : '';
}

export function debugCsrf() {
  const cookie = getCsrfToken();
  console.log('CSRF Token in cookie:', cookie);
  console.log('All cookies:', document.cookie);
  return cookie;
}

api.interceptors.request.use(config => {
  if (config.method !== 'get') {
    const token = getCsrfToken();
    config.headers['X-CSRF-Token'] = token;
    if (import.meta.env.DEV) {
      console.log(`Adding CSRF token to ${config.url}:`, token);
    }
  }

  const token = localStorage.getItem('access_token') ||
               localStorage.getItem('token') ||
               localStorage.getItem('regular_token') ||
               localStorage.getItem('google_auth_token');

  if (token) {
    config.headers['Authorization'] = `Bearer ${token}`;
  }

  return config;
});

// Refresh token queue state
let isRefreshing = false;
let failedQueue: Array<{ resolve: (value: string) => void; reject: (reason?: unknown) => void }> = [];

function processQueue(error: unknown, token: string | null = null) {
  failedQueue.forEach(prom => {
    if (error) {
      prom.reject(error);
    } else {
      prom.resolve(token as string);
    }
  });
  failedQueue = [];
}

function clearAuthTokens() {
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
  localStorage.removeItem('regular_token');
  localStorage.removeItem('google_auth_token');
  localStorage.removeItem('user_id');
  localStorage.removeItem('user_email');
  localStorage.removeItem('user_provider');
  delete axios.defaults.headers.common['Authorization'];
}

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    if (error.response?.status !== 401 || originalRequest._retry) {
      return Promise.reject(error);
    }

    // Don't retry auth endpoints
    const url: string = originalRequest.url || '';
    if (url.includes('/auth/refresh') || url.includes('/login') || url.includes('/registration')) {
      return Promise.reject(error);
    }

    const refreshToken = localStorage.getItem('refresh_token');
    if (!refreshToken) {
      clearAuthTokens();
      window.location.href = '/login';
      return Promise.reject(error);
    }

    if (isRefreshing) {
      return new Promise<string>((resolve, reject) => {
        failedQueue.push({ resolve, reject });
      }).then(token => {
        originalRequest.headers['Authorization'] = `Bearer ${token}`;
        return api(originalRequest);
      }).catch(err => Promise.reject(err));
    }

    originalRequest._retry = true;
    isRefreshing = true;

    try {
      const { data } = await axios.post(`${API_URL}/auth/refresh`, {
        refresh_token: refreshToken
      });

      localStorage.setItem('access_token', data.access_token);
      localStorage.setItem('refresh_token', data.refresh_token);
      localStorage.setItem('regular_token', data.access_token);

      axios.defaults.headers.common['Authorization'] = `Bearer ${data.access_token}`;
      originalRequest.headers['Authorization'] = `Bearer ${data.access_token}`;

      processQueue(null, data.access_token);
      return api(originalRequest);
    } catch (err) {
      processQueue(err, null);
      clearAuthTokens();
      window.location.href = '/login';
      return Promise.reject(err);
    } finally {
      isRefreshing = false;
    }
  }
);

export default api;
