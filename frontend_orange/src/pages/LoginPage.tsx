import React, { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import api from '../services/api';
import { AuthAside } from '../components/auth/AuthAside';
import { SSORow } from '../components/auth/SSORow';

const LoginPage: React.FC = () => {
  const { isAuthenticated, login } = useAuth();
  const navigate = useNavigate();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showMagic, setShowMagic] = useState(false);
  const [magicSent, setMagicSent] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (isAuthenticated) navigate('/dashboard', { replace: true });
  }, [isAuthenticated, navigate]);

  const handleGoogleLogin = () => {
    const API_BASE = import.meta.env.VITE_API_URL?.replace('/api/v1', '') || 'http://localhost:8080';
    const popup = window.open(`${API_BASE}/api/v1/auth/login`, 'google-auth', 'width=500,height=600,left=200,top=100');
    const handler = async (event: MessageEvent) => {
      if (event.data?.type !== 'google_auth_success') return;
      window.removeEventListener('message', handler);
      popup?.close();
      const success = await login(event.data.access_token, event.data.refresh_token);
      if (success) navigate('/dashboard');
      else setError('Authentication failed.');
    };
    window.addEventListener('message', handler);
    const t = setInterval(() => {
      if (popup?.closed) { clearInterval(t); window.removeEventListener('message', handler); }
    }, 500);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim() || !password) return setError('Please enter your email and password.');
    setLoading(true);
    setError('');
    try {
      const res = await api.post('/login', { email_address: email.trim(), password });
      const success = await login(res.data.access_token, res.data.refresh_token);
      if (success) navigate('/dashboard');
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

  const sendMagic = () => {
    if (!email.trim()) return setError('Enter your email first.');
    setMagicSent(true);
    setError('');
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

          {!magicSent ? (
            <form onSubmit={handleSubmit} className="animate-fade-up">
              <h1 className="auth-title">Welcome back.</h1>
              <p className="auth-sub">Sign in to continue aligning your scope.</p>

              <SSORow onGoogle={handleGoogleLogin} />
              <div className="divider">or with credentials</div>

              <div className="field">
                <label>Email address</label>
                <input className="input" type="email" value={email} onChange={e => { setEmail(e.target.value); setError(''); }} placeholder="ada@acme.com" autoComplete="email" autoFocus />
              </div>

              {!showMagic && (
                <div className="field">
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <label>Password</label>
                    <button
                      type="button"
                      onClick={() => setShowMagic(true)}
                      style={{ background: 'none', border: 'none', color: 'var(--accent)', fontSize: 12, cursor: 'pointer', padding: 0, fontFamily: 'inherit' }}
                    >
                      Use magic link
                    </button>
                  </div>
                  <input className="input" type="password" value={password} onChange={e => { setPassword(e.target.value); setError(''); }} placeholder="••••••••" autoComplete="current-password" />
                </div>
              )}

              {showMagic ? (
                <>
                  <button type="button" onClick={sendMagic} className="btn btn-primary auth-submit btn-lg">Send magic link →</button>
                  <button type="button" onClick={() => setShowMagic(false)} style={{ display: 'block', margin: '16px auto 0', background: 'none', border: 'none', color: 'var(--fg-dim)', fontSize: 13, cursor: 'pointer' }}>
                    ← Use password instead
                  </button>
                </>
              ) : (
                <button type="submit" disabled={loading} className="btn btn-primary auth-submit btn-lg">
                  {loading ? 'Signing in…' : 'Sign in →'}
                </button>
              )}

              <div className="auth-footer-link">
                Don't have an account? <Link to="/signup">Sign up free</Link>
              </div>
            </form>
          ) : (
            <div className="success-card animate-fade-up">
              <div className="success-icon">
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" /><polyline points="22,6 12,13 2,6" /></svg>
              </div>
              <h1 className="auth-title" style={{ fontSize: 32 }}>Magic link sent.</h1>
              <p className="auth-sub">
                We sent a one-click sign-in link to <strong style={{ color: 'var(--fg)' }}>{email}</strong>. Check your inbox — it'll expire in 15 minutes.
              </p>
              <button
                type="button"
                onClick={() => { setMagicSent(false); setShowMagic(false); }}
                className="btn btn-ghost auth-submit btn-lg"
              >
                ← Back to sign in
              </button>
            </div>
          )}
        </div>
      </main>
    </div>
  );
};

export default LoginPage;
