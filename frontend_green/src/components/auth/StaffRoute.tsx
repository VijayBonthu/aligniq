import { ReactNode } from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';

/**
 * Route guard for the platform /admin ops console. Allows only GroundedIQ staff
 * (user.is_staff). Unauthenticated → /login; authenticated non-staff → /projects
 * (no dead-end 403). The backend independently enforces require_staff on every
 * /admin endpoint, so this is UX-only, not the security boundary.
 */
export default function StaffRoute({ children }: { children: ReactNode }) {
  const { isAuthenticated, authReady, user } = useAuth();
  if (!authReady) return null;
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  if (!user?.is_staff) return <Navigate to="/projects" replace />;
  return <>{children}</>;
}
