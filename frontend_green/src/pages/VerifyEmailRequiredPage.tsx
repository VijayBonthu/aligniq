import React, { useState, useEffect } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';
import { AuthAside } from '../components/auth/AuthAside';

// Shown to a signed-in but UNVERIFIED Local user (ProtectedRoute redirects them here).
// SSO users are provider-verified and never see this. Verified users who land here are
// sent on to /projects.
const VerifyEmailRequiredPage: React.FC = () => {
  const { isAuthenticated, authReady, user, login, logout } = useAuth();
  const navigate = useNavigate();
  const [resending, setResending] = useState(false);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState('');
  const [cooldown, setCooldown] = useState(0); // seconds until "Resend" re-enables

  // Tick the resend cooldown down once a second.
  useEffect(() => {
    if (cooldown <= 0) return;
    const t = setTimeout(() => setCooldown((c) => c - 1), 1000);
    return () => clearTimeout(t);
  }, [cooldown]);

  if (!authReady) return null;
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  if (user && user.verified_email !== false) return <Navigate to="/projects" replace />;

  const resend = async () => {
    if (cooldown > 0 || resending) return;
    setResending(true);
    setError('');
    try {
      const { data } = await api.post('/auth/resend-verification');
      toast.success('Verification email sent.');
      setCooldown(data?.cooldown || 60); // start the countdown so they can't spam it
    } catch (err: unknown) {
      const e = err as { response?: { status?: number; data?: { detail?: { retry_after?: number } } } };
      if (e.response?.status === 429) {
        const ra = e.response.data?.detail?.retry_after || 60;
        setCooldown(ra);
        setError(`Please wait ${ra}s before requesting another email.`);
      } else {
        setError('Could not resend right now. Please try again in a moment.');
      }
    } finally {
      setResending(false);
    }
  };

  // After the user clicks the link (in this or another tab), refresh the session so the
  // new verified_email=true token is picked up, then continue into the app.
  const continueAfterVerify = async () => {
    setChecking(true);
    setError('');
    try {
      const { data } = await api.post('/auth/refresh');
      const ok = await login(data.access_token);
      if (ok) navigate('/projects');
      else setError('Still unverified. Click the link in your email, then try again.');
    } catch {
      setError('Still unverified. Click the link in your email, then try again.');
    } finally {
      setChecking(false);
    }
  };

  return (
    <div className="auth-wrap">
      <AuthAside />

      <main className="auth-main">
        <div className="auth-form-wrap">
          {error && (
            <div className="animate-fade-up" style={{ padding: '10px 14px', background: 'rgba(255,106,106,0.08)', border: '1px solid rgba(255,106,106,0.2)', borderRadius: 10, marginBottom: 16, color: 'var(--danger)', fontSize: 13 }}>
              {error}
            </div>
          )}

          <div className="animate-fade-up">
            <div className="auth-eyebrow">One more step</div>
            <h1 className="auth-title">Verify your email.</h1>
            <p className="auth-sub">
              We sent a confirmation link to <strong style={{ color: 'var(--fg)' }}>{user?.email}</strong>.
              Click it to activate your account, then continue.
            </p>

            <button type="button" onClick={continueAfterVerify} disabled={checking} className="btn btn-primary auth-submit btn-lg">
              {checking ? 'Checking…' : "I've verified — continue →"}
            </button>

            <button type="button" onClick={resend} disabled={resending || cooldown > 0} className="btn btn-ghost auth-submit btn-lg" style={{ marginTop: 12 }}>
              {cooldown > 0 ? `Resend in ${cooldown}s` : resending ? 'Sending…' : 'Resend the email'}
            </button>

            <button
              type="button"
              onClick={() => { logout(); navigate('/login'); }}
              style={{ display: 'block', margin: '18px auto 0', background: 'none', border: 'none', color: 'var(--fg-dim)', fontSize: 13, cursor: 'pointer', fontFamily: 'inherit' }}
            >
              Sign out
            </button>
          </div>
        </div>
      </main>
    </div>
  );
};

export default VerifyEmailRequiredPage;
