import React, { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import api from '../services/api';
import { useOAuthPopup } from '../hooks/useOAuthPopup';
import { AuthAside } from '../components/auth/AuthAside';
import { SSORow } from '../components/auth/SSORow';

const LoginPage: React.FC = () => {
  const { isAuthenticated, authReady, login } = useAuth();
  const navigate = useNavigate();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showForgot, setShowForgot] = useState(false);
  const [forgotSent, setForgotSent] = useState(false);
  const [forgotSending, setForgotSending] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const startGoogleAuth = useOAuthPopup('google', setError);
  const startGithubAuth = useOAuthPopup('github', setError);
  const startMicrosoftAuth = useOAuthPopup('microsoft', setError);

  useEffect(() => {
    if (authReady && isAuthenticated) navigate('/projects', { replace: true });
  }, [authReady, isAuthenticated, navigate]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim() || !password) return setError('Please enter your email and password.');
    setLoading(true);
    setError('');
    try {
      const res = await api.post('/login', { email_address: email.trim(), password });
      const success = await login(res.data.access_token);
      if (success) navigate('/projects');
      else setError('Login failed.');
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'response' in err) {
        const axErr = err as { response?: { status?: number; data?: { detail?: string } } };
        if (axErr.response?.status === 401) setError('Incorrect email or password.');
        else if (axErr.response?.status === 404) setError('Account not found.');
        else setError(axErr.response?.data?.detail || 'Login failed.');
      } else setError('Something went wrong.');
    } finally {
      setLoading(false);
    }
  };

  const sendReset = async () => {
    if (!email.trim()) return setError('Enter your email first.');
    setForgotSending(true);
    setError('');
    try {
      // Always succeeds server-side (no account enumeration); we just confirm it's away.
      await api.post('/auth/forgot-password', { email: email.trim() });
      setForgotSent(true);
    } catch {
      setError('Could not send the reset link. Please try again.');
    } finally {
      setForgotSending(false);
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

          {forgotSent ? (
            <div className="success-card animate-fade-up">
              <div className="success-icon">
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" /><polyline points="22,6 12,13 2,6" /></svg>
              </div>
              <h1 className="auth-title" style={{ fontSize: 32 }}>Check your inbox.</h1>
              <p className="auth-sub">
                If an account exists for <strong style={{ color: 'var(--fg)' }}>{email}</strong>, we've sent a link to reset your password. It expires in 15 minutes.
              </p>
              <button
                type="button"
                onClick={() => { setForgotSent(false); setShowForgot(false); }}
                className="btn btn-ghost auth-submit btn-lg"
              >
                ← Back to sign in
              </button>
            </div>
          ) : (
            <form onSubmit={showForgot ? (e) => { e.preventDefault(); sendReset(); } : handleSubmit} className="animate-fade-up">
              <div className="auth-eyebrow">{showForgot ? 'Account recovery' : 'Welcome back'}</div>
              <h1 className="auth-title">{showForgot ? 'Reset your password.' : 'Welcome back.'}</h1>
              <p className="auth-sub">
                {showForgot
                  ? "Enter your email and we'll send a link to set a new password."
                  : 'Sign in to continue scoping with confidence.'}
              </p>

              {!showForgot && (
                <>
                  <SSORow onGoogle={startGoogleAuth} onGithub={startGithubAuth} onMicrosoft={startMicrosoftAuth} />
                  <div className="divider">or with credentials</div>
                </>
              )}

              <div className="field">
                <label>Email address</label>
                <input className="input" type="email" value={email} onChange={e => { setEmail(e.target.value); setError(''); }} placeholder="ada@acme.com" autoComplete="email" autoFocus />
              </div>

              {!showForgot && (
                <div className="field">
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <label>Password</label>
                    <button
                      type="button"
                      onClick={() => { setShowForgot(true); setError(''); }}
                      style={{ background: 'none', border: 'none', color: 'var(--accent)', fontSize: 12, cursor: 'pointer', padding: 0, fontFamily: 'inherit' }}
                    >
                      Forgot password?
                    </button>
                  </div>
                  <input className="input" type="password" value={password} onChange={e => { setPassword(e.target.value); setError(''); }} placeholder="••••••••" autoComplete="current-password" />
                </div>
              )}

              {showForgot ? (
                <>
                  <button type="submit" disabled={forgotSending} className="btn btn-primary auth-submit btn-lg">
                    {forgotSending ? 'Sending…' : 'Send reset link →'}
                  </button>
                  <button type="button" onClick={() => { setShowForgot(false); setError(''); }} style={{ display: 'block', margin: '16px auto 0', background: 'none', border: 'none', color: 'var(--fg-dim)', fontSize: 13, cursor: 'pointer', fontFamily: 'inherit' }}>
                    ← Back to sign in
                  </button>
                </>
              ) : (
                <button type="submit" disabled={loading} className="btn btn-primary auth-submit btn-lg">
                  {loading ? 'Signing in…' : 'Sign in →'}
                </button>
              )}

              {!showForgot && (
                <div className="auth-footer-link">
                  Don't have an account? <Link to="/signup">Sign up free</Link>
                </div>
              )}
            </form>
          )}
        </div>
      </main>
    </div>
  );
};

export default LoginPage;
