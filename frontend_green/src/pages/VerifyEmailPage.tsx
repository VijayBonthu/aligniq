import React, { useEffect, useState, useRef } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';
import { AuthAside } from '../components/auth/AuthAside';

type Status = 'verifying' | 'done' | 'error';

const VerifyEmailPage: React.FC = () => {
  const [params] = useSearchParams();
  const token = params.get('token') || '';
  const navigate = useNavigate();
  const { login } = useAuth();

  const [status, setStatus] = useState<Status>(token ? 'verifying' : 'error');
  const [error, setError] = useState(token ? '' : 'This verification link is missing or malformed.');
  // If they're signed in on THIS browser, refresh picks up verified=true → go to /projects;
  // if not (link opened elsewhere), send them to /login to sign in.
  const [loggedInHere, setLoggedInHere] = useState(false);
  const ranRef = useRef(false);

  useEffect(() => {
    if (!token || ranRef.current) return;
    ranRef.current = true; // guard against React StrictMode's double-invoke
    (async () => {
      try {
        await api.post('/auth/verify-email', { token });
        // Re-mint this session's token so the new verified_email=true is reflected and the
        // route gate lets them in. No-op (caught) if they aren't logged in on this browser.
        try {
          const { data } = await api.post('/auth/refresh');
          await login(data.access_token);
          setLoggedInHere(true);
        } catch { /* not signed in here — they'll log in */ }
        setStatus('done');
      } catch (err: unknown) {
        if (err && typeof err === 'object' && 'response' in err) {
          const axErr = err as { response?: { data?: { detail?: string } } };
          setError(axErr.response?.data?.detail || 'This verification link is invalid or has expired.');
        } else setError('Something went wrong. Please try again.');
        setStatus('error');
      }
    })();
  }, [token, login]);

  return (
    <div className="auth-wrap">
      <AuthAside />

      <main className="auth-main">
        <div className="auth-form-wrap">
          {status === 'verifying' && (
            <div className="animate-fade-up">
              <div className="auth-eyebrow">Email verification</div>
              <h1 className="auth-title">Confirming your email…</h1>
              <p className="auth-sub">One moment while we verify your link.</p>
            </div>
          )}

          {status === 'done' && (
            <div className="success-card animate-fade-up">
              <div className="success-icon">
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12" /></svg>
              </div>
              <h1 className="auth-title" style={{ fontSize: 32 }}>Email confirmed.</h1>
              <p className="auth-sub">Your account is secured. You're all set.</p>
              <button type="button" className="btn btn-primary auth-submit btn-lg" onClick={() => navigate(loggedInHere ? '/projects' : '/login')}>
                {loggedInHere ? 'Continue →' : 'Sign in →'}
              </button>
            </div>
          )}

          {status === 'error' && (
            <div className="animate-fade-up">
              <div className="auth-eyebrow">Email verification</div>
              <h1 className="auth-title">Link not valid.</h1>
              <p className="auth-sub">{error} You can request a fresh link from your account once signed in.</p>
              <Link to="/login" className="btn btn-primary auth-submit btn-lg" style={{ display: 'inline-flex', justifyContent: 'center' }}>
                Back to sign in →
              </Link>
            </div>
          )}
        </div>
      </main>
    </div>
  );
};

export default VerifyEmailPage;
