import { useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Toaster } from 'react-hot-toast';
import { AuthProvider, useAuth } from './context/AuthContext';
import { SiteConfigProvider } from './context/SiteConfigContext';
import MaintenanceGate from './components/ops/MaintenanceGate';
import { ThemeProvider } from './context/ThemeContext';
import ThemeToggle from './components/layout/ThemeToggle';
import LandingPage from './pages/LandingPage';
import SignupPage from './pages/SignupPage';
import LoginPage from './pages/LoginPage';
import ResetPasswordPage from './pages/ResetPasswordPage';
import VerifyEmailPage from './pages/VerifyEmailPage';
import VerifyEmailRequiredPage from './pages/VerifyEmailRequiredPage';
import PublicQuestionnaire from './pages/PublicQuestionnaire';
import Dashboard from './pages/Dashboard';
import ProjectsPage from './pages/ProjectsPage';
import NewProjectFlow from './pages/NewProjectFlow';
import ChatView from './pages/ChatView';
import CompareView from './pages/CompareView';
import FullPipelineProgress from './pages/FullPipelineProgress';
import DeliverableBuilder from './pages/DeliverableBuilder';
import Messages from './pages/Messages';
import Reports from './pages/Reports';
import Settings from './pages/Settings';
import PricingPage from './pages/PricingPage';
import ContactPage from './pages/ContactPage';
import AboutPage from './pages/AboutPage';
import SecurityPage from './pages/SecurityPage';
import CareersPage from './pages/CareersPage';
import ChangelogPage from './pages/ChangelogPage';
import TermsPage from './pages/legal/TermsPage';
import PrivacyPage from './pages/legal/PrivacyPage';
import AppShell from './components/layout/AppShell';
import ErrorBoundary from './components/ErrorBoundary';
import UpgradeModal from './components/billing/UpgradeModal';
import FirmAdminRoute from './components/auth/FirmAdminRoute';
import StaffRoute from './components/auth/StaffRoute';
import AdminConsole from './pages/admin/AdminConsole';
import FirmSettings from './pages/firm/FirmSettings';
import RateCardPage from './pages/firm/RateCard';
import TeamTemplatesPage from './pages/firm/TeamTemplates';
import TechPreferencesPage from './pages/firm/TechPreferences';
import PastProjectsPage from './pages/firm/PastProjects';
import PastProjectEditor from './pages/firm/PastProjectEditor';

function BgLayers() {
  const { pathname } = useLocation();
  if (
    pathname.startsWith('/dashboard') ||
    pathname.startsWith('/projects') ||
    pathname.startsWith('/new-project') ||
    pathname.startsWith('/chat') ||
    pathname.startsWith('/compare') ||
    pathname.startsWith('/full-pipeline') ||
    pathname.startsWith('/deliverable') ||
    pathname.startsWith('/messages') ||
    pathname.startsWith('/reports') ||
    pathname.startsWith('/settings') ||
    pathname.startsWith('/firm') ||
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

// Pages outside AppShell have no rail to host the theme switch, so float one in
// the corner. Landing carries its own toggle in the nav, hence it's excluded.
function PublicThemeToggle() {
  const { pathname } = useLocation();
  // NOTE: the client questionnaire (/q/:token) is a fixed, firm-branded surface — it
  // deliberately has NO theme toggle (a floating toggle there only flipped itself, not
  // the page, which read as "dark mode is broken").
  const onPublic = pathname === '/login' || pathname === '/signup' || pathname === '/reset-password' || pathname === '/verify-email' || pathname === '/verify-email-required' || pathname === '/pricing';
  return onPublic ? <ThemeToggle floating /> : null;
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
  const { isAuthenticated, authReady, user } = useAuth();
  // Wait for the on-mount silent refresh (httpOnly cookie → access token) to resolve;
  // otherwise a hard reload of a protected page would redirect a live session to /login.
  if (!authReady) return null;
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  // Unverified (Local) users can't use the app until they confirm their email. SSO logins
  // are provider-verified (verified_email=true), so only unverified Local accounts hit this.
  if (user && user.verified_email === false) return <Navigate to="/verify-email-required" replace />;
  return <>{children}</>;
}

function App() {
  return (
    <ErrorBoundary>
    <BrowserRouter>
      <QueryClientProvider client={queryClient}>
        <ThemeProvider>
        <AuthProvider>
          <SiteConfigProvider>
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
          <PublicThemeToggle />
          <GlobalUpgradeModal />
          <UpgradeReturnRefresher />
          <MaintenanceGate>
          <Routes>
            <Route path="/" element={<LandingPage />} />
            <Route path="/login" element={<LoginPage />} />
            <Route path="/signup" element={<SignupPage />} />
            <Route path="/reset-password" element={<ResetPasswordPage />} />
            <Route path="/verify-email" element={<VerifyEmailPage />} />
            <Route path="/verify-email-required" element={<VerifyEmailRequiredPage />} />
            <Route path="/pricing" element={<PricingPage />} />
            <Route path="/contact" element={<ContactPage />} />
            <Route path="/about" element={<AboutPage />} />
            <Route path="/security" element={<SecurityPage />} />
            <Route path="/careers" element={<CareersPage />} />
            <Route path="/changelog" element={<ChangelogPage />} />
            <Route path="/q/:token" element={<PublicQuestionnaire />} />
            <Route path="/terms" element={<TermsPage />} />
            <Route path="/privacy" element={<PrivacyPage />} />
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
              path="/compare/:chatHistoryId"
              element={
                <ProtectedRoute>
                  <AppShell>
                    <CompareView />
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
              path="/deliverable/:chatHistoryId"
              element={
                <ProtectedRoute>
                  <AppShell>
                    <DeliverableBuilder />
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
              path="/admin"
              element={
                <StaffRoute>
                  <AppShell>
                    <AdminConsole />
                  </AppShell>
                </StaffRoute>
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
            <Route
              path="/firm/settings"
              element={
                <FirmAdminRoute>
                  <AppShell>
                    <FirmSettings />
                  </AppShell>
                </FirmAdminRoute>
              }
            />
            <Route
              path="/firm/rate-cards"
              element={
                <FirmAdminRoute>
                  <AppShell>
                    <RateCardPage />
                  </AppShell>
                </FirmAdminRoute>
              }
            />
            <Route
              path="/firm/team-templates"
              element={
                <FirmAdminRoute>
                  <AppShell>
                    <TeamTemplatesPage />
                  </AppShell>
                </FirmAdminRoute>
              }
            />
            <Route
              path="/firm/tech-preferences"
              element={
                <FirmAdminRoute>
                  <AppShell>
                    <TechPreferencesPage />
                  </AppShell>
                </FirmAdminRoute>
              }
            />
            <Route
              path="/firm/past-projects"
              element={
                <FirmAdminRoute>
                  <AppShell>
                    <PastProjectsPage />
                  </AppShell>
                </FirmAdminRoute>
              }
            />
            <Route
              path="/firm/past-projects/new"
              element={
                <FirmAdminRoute>
                  <AppShell>
                    <PastProjectEditor />
                  </AppShell>
                </FirmAdminRoute>
              }
            />
            <Route
              path="/firm/past-projects/:projectId"
              element={
                <FirmAdminRoute>
                  <AppShell>
                    <PastProjectEditor />
                  </AppShell>
                </FirmAdminRoute>
              }
            />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
          </MaintenanceGate>
          </SiteConfigProvider>
        </AuthProvider>
        </ThemeProvider>
      </QueryClientProvider>
    </BrowserRouter>
    </ErrorBoundary>
  );
}

export default App;
