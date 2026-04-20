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

api.interceptors.request.use(config => {
  if (config.method !== 'get') {
    config.headers['X-CSRF-Token'] = getCsrfToken();
  }

  const token =
    localStorage.getItem('access_token') ||
    localStorage.getItem('regular_token') ||
    localStorage.getItem('google_auth_token');

  if (token) {
    config.headers['Authorization'] = `Bearer ${token}`;
  }

  return config;
});

let isRefreshing = false;
let failedQueue: Array<{ resolve: (v: string) => void; reject: (r?: unknown) => void }> = [];

function processQueue(error: unknown, token: string | null = null) {
  failedQueue.forEach(p => (error ? p.reject(error) : p.resolve(token as string)));
  failedQueue = [];
}

function clearAuthTokens() {
  ['access_token', 'refresh_token', 'regular_token', 'google_auth_token',
   'user_id', 'user_email', 'user_provider'].forEach(k => localStorage.removeItem(k));
  delete api.defaults.headers.common['Authorization'];
}

api.interceptors.response.use(
  response => response,
  async error => {
    const original = error.config;

    if (error.response?.status !== 401 || original._retry) {
      return Promise.reject(error);
    }

    const url: string = original.url || '';
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
        original.headers['Authorization'] = `Bearer ${token}`;
        return api(original);
      });
    }

    original._retry = true;
    isRefreshing = true;

    try {
      const { data } = await api.post('/auth/refresh', { refresh_token: refreshToken });
      localStorage.setItem('access_token', data.access_token);
      localStorage.setItem('refresh_token', data.refresh_token);
      localStorage.setItem('regular_token', data.access_token);
      api.defaults.headers.common['Authorization'] = `Bearer ${data.access_token}`;
      original.headers['Authorization'] = `Bearer ${data.access_token}`;
      processQueue(null, data.access_token);
      return api(original);
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
