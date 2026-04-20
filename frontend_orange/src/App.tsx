import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Toaster } from 'react-hot-toast';
import { AuthProvider, useAuth } from './context/AuthContext';
import LandingPage from './pages/LandingPage';
import SignupPage from './pages/SignupPage';
import LoginPage from './pages/LoginPage';
import Dashboard from './pages/Dashboard';

function BgLayers() {
  const { pathname } = useLocation();
  if (pathname.startsWith('/dashboard')) return null;
  return (
    <>
      <div className="bg-grid-layer" aria-hidden />
      <div className="bg-aurora-layer" aria-hidden />
    </>
  );
}

const queryClient = new QueryClient();

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuth();
  return isAuthenticated ? <>{children}</> : <Navigate to="/login" replace />;
}

function App() {
  return (
    <BrowserRouter>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <Toaster
            position="top-right"
            toastOptions={{
              style: {
                background: 'var(--surface)',
                color: 'var(--fg)',
                border: '1px solid var(--border-strong)',
                borderRadius: '8px',
                fontFamily: '"Inter Tight", sans-serif',
                fontSize: '14px',
              },
              success: { iconTheme: { primary: 'var(--ok)', secondary: 'var(--bg)' } },
              error: { iconTheme: { primary: 'var(--danger)', secondary: 'var(--bg)' } },
            }}
          />
          <BgLayers />
          <Routes>
            <Route path="/" element={<LandingPage />} />
            <Route path="/login" element={<LoginPage />} />
            <Route path="/signup" element={<SignupPage />} />
            <Route
              path="/dashboard"
              element={
                <ProtectedRoute>
                  <Dashboard />
                </ProtectedRoute>
              }
            />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </AuthProvider>
      </QueryClientProvider>
    </BrowserRouter>
  );
}

export default App;
