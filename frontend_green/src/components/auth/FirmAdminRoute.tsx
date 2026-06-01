import { ReactNode } from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';

/**
 * Route guard that allows only firm admins (firm_role === 'firm_admin').
 * Unauthenticated users go to /login; authenticated non-admins go to /projects
 * so they don't see a 403 page they can't escape.
 */
export default function FirmAdminRoute({ children }: { children: ReactNode }) {
  const { isAuthenticated, user } = useAuth();
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  if (user && user.firm_role !== 'firm_admin') return <Navigate to="/projects" replace />;
  return <>{children}</>;
}
