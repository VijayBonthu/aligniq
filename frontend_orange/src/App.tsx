import { useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Toaster } from 'react-hot-toast';
import { AuthProvider, useAuth } from './context/AuthContext';
import LandingPage from './pages/LandingPage';
import SignupPage from './pages/SignupPage';
import LoginPage from './pages/LoginPage';
import Dashboard from './pages/Dashboard';
import ProjectsPage from './pages/ProjectsPage';
import NewProjectFlow from './pages/NewProjectFlow';
import ChatView from './pages/ChatView';
import FullPipelineProgress from './pages/FullPipelineProgress';
import Messages from './pages/Messages';
import Reports from './pages/Reports';
import Settings from './pages/Settings';
import PricingPage from './pages/PricingPage';
import AppShell from './components/layout/AppShell';
import UpgradeModal from './components/billing/UpgradeModal';

function BgLayers() {
  const { pathname } = useLocation();
  if (
    pathname.startsWith('/dashboard') ||
    pathname.startsWith('/projects') ||
    pathname.startsWith('/new-project') ||
    pathname.startsWith('/chat') ||
    pathname.startsWith('/full-pipeline') ||
    pathname.startsWith('/messages') ||
    pathname.startsWith('/reports') ||
    pathname.startsWith('/settings') ||
    pathname.startsWith('/pricing')
  )
    return null;
  return (
    <>
      <div className="bg-grid-layer" aria-hidden />
      <div className="bg-aurora-layer" aria-hidden />
    </>
  );
}

function GlobalUpgradeModal() {
  const { limitHit, clearLimitHit } = useAuth();
  return <UpgradeModal open={!!limitHit} detail={limitHit} onClose={clearLimitHit} />;
}

// Stripe Checkout / Customer Portal redirect users back to any page in the app
// with ?upgrade=success. Refresh the cached subscription once and strip the
// param so a refresh won't refire it. Mounted once so every route benefits.
function UpgradeReturnRefresher() {
  const { isAuthenticated, refreshSubscription } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  useEffect(() => {
    if (!isAuthenticated) return;
    const params = new URLSearchParams(location.search);
    if (params.get('upgrade') !== 'success') return;
    refreshSubscription();
    params.delete('upgrade');
    const search = params.toString();
    navigate(
      { pathname: location.pathname, search: search ? `?${search}` : '' },
      { replace: true },
    );
  }, [isAuthenticated, location.search, location.pathname, navigate, refreshSubscription]);
  return null;
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
          <GlobalUpgradeModal />
          <UpgradeReturnRefresher />
          <Routes>
            <Route path="/" element={<LandingPage />} />
            <Route path="/login" element={<LoginPage />} />
            <Route path="/signup" element={<SignupPage />} />
            <Route path="/pricing" element={<PricingPage />} />
            <Route
              path="/projects"
              element={
                <ProtectedRoute>
                  <AppShell>
                    <ProjectsPage />
                  </AppShell>
                </ProtectedRoute>
              }
            />
            <Route
              path="/new-project"
              element={
                <ProtectedRoute>
                  <AppShell>
                    <NewProjectFlow />
                  </AppShell>
                </ProtectedRoute>
              }
            />
            <Route
              path="/new-project/:chatHistoryId"
              element={
                <ProtectedRoute>
                  <AppShell>
                    <NewProjectFlow />
                  </AppShell>
                </ProtectedRoute>
              }
            />
            <Route
              path="/chat/:chatHistoryId"
              element={
                <ProtectedRoute>
                  <AppShell>
                    <ChatView />
                  </AppShell>
                </ProtectedRoute>
              }
            />
            <Route
              path="/full-pipeline/:chatHistoryId"
              element={
                <ProtectedRoute>
                  <AppShell>
                    <FullPipelineProgress />
                  </AppShell>
                </ProtectedRoute>
              }
            />
            <Route
              path="/messages"
              element={
                <ProtectedRoute>
                  <AppShell>
                    <Messages />
                  </AppShell>
                </ProtectedRoute>
              }
            />
            <Route
              path="/reports"
              element={
                <ProtectedRoute>
                  <AppShell>
                    <Reports />
                  </AppShell>
                </ProtectedRoute>
              }
            />
            <Route
              path="/settings"
              element={
                <ProtectedRoute>
                  <AppShell>
                    <Settings />
                  </AppShell>
                </ProtectedRoute>
              }
            />
            <Route
              path="/dashboard"
              element={
                <ProtectedRoute>
                  <Dashboard />
                </ProtectedRoute>
              }
            />
            <Route
              path="/dashboard/:chatHistoryId"
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
