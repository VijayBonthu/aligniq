import React, { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import api from '../services/api';
import { AuthAside } from '../components/auth/AuthAside';
import { SSORow } from '../components/auth/SSORow';

const ROLES: { label: string; desc: string }[] = [
  { label: 'Product Manager',    desc: 'I scope and track projects.' },
  { label: 'Solution Architect', desc: 'I design the how, not just the what.' },
  { label: 'Consultant',         desc: 'I scope & deliver for clients.' },
  { label: 'Client',             desc: 'I commission work from agencies.' },
];

const passwordStrength = (pw: string): { score: 0 | 1 | 2 | 3 | 4; label: string } => {
  if (!pw) return { score: 0, label: 'Empty' };
  let s = 0;
  if (pw.length >= 8) s++;
  if (pw.length >= 12) s++;
  if (/[A-Z]/.test(pw) && /[a-z]/.test(pw)) s++;
  if (/\d/.test(pw) && /[^A-Za-z0-9]/.test(pw)) s++;
  const label = ['Weak', 'Weak', 'Fair', 'Strong', 'Excellent'][s] || 'Weak';
  return { score: s as 0 | 1 | 2 | 3 | 4, label };
};

const SignupPage: React.FC = () => {
  const { isAuthenticated, login } = useAuth();
  const navigate = useNavigate();

  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [fullName, setFullName] = useState('');
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [company, setCompany] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState<string>('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (isAuthenticated && step !== 3) navigate('/dashboard', { replace: true });
  }, [isAuthenticated, navigate, step]);

  const strength = passwordStrength(password);

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

  const handleStep1 = (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    if (!fullName.trim() || !username.trim() || !email.trim() || !password) {
      setError('Please fill in your name, username, email, and password.');
      return;
    }
    if (username.length < 3) return setError('Username must be at least 3 characters.');
    if (password.length < 8) return setError('Password must be at least 8 characters.');
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return setError('Please enter a valid email.');
    setStep(2);
  };

  const completeSignup = async (selectedRole: string) => {
    setRole(selectedRole);
    setSubmitting(true);
    setError('');
    const [given_name, ...rest] = fullName.trim().split(/\s+/);
    const family_name = rest.join(' ') || '-';
    try {
      const res = await api.post('/registration', {
        email: email.trim(),
        given_name,
        family_name,
        password,
        username: username.trim(),
        role: selectedRole,
      });
      const success = await login(res.data.access_token, res.data.refresh_token);
      if (!success) throw new Error('Login after signup failed');
      setTimeout(() => setStep(3), 700);
    } catch (err: unknown) {
      setSubmitting(false);
      if (err && typeof err === 'object' && 'response' in err) {
        const axErr = err as { response?: { status?: number; data?: { detail?: string } } };
        if (axErr.response?.status === 409) setError('An account with that email or username already exists.');
        else setError(axErr.response?.data?.detail || 'Signup failed. Please try again.');
      } else setError('Something went wrong. Please try again.');
      setStep(1);
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

          {step === 1 && (
            <form onSubmit={handleStep1} className="animate-fade-up">
              <h1 className="auth-title">Create your account.</h1>
              <p className="auth-sub">Start aligning your next project in under a minute.</p>

              <SSORow onGoogle={handleGoogleLogin} />
              <div className="divider">or with email</div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 16 }}>
                <div className="field" style={{ margin: 0 }}>
                  <label>Full name</label>
                  <input className="input" value={fullName} onChange={e => setFullName(e.target.value)} placeholder="Ada Lovelace" autoComplete="name" />
                </div>
                <div className="field" style={{ margin: 0 }}>
                  <label>Username</label>
                  <input className="input" value={username} onChange={e => setUsername(e.target.value.toLowerCase().replace(/\s/g, ''))} placeholder="ada" autoComplete="username" />
                </div>
              </div>

              <div className="field">
                <label>Work email</label>
                <input className="input" type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="ada@acme.com" autoComplete="email" />
              </div>

              <div className="field">
                <label>Company <span style={{ opacity: 0.5, textTransform: 'none' }}>(optional)</span></label>
                <input className="input" value={company} onChange={e => setCompany(e.target.value)} placeholder="Acme Consulting" autoComplete="organization" />
              </div>

              <div className="field">
                <label>Password</label>
                <input className="input" type="password" value={password} onChange={e => setPassword(e.target.value)} placeholder="At least 8 characters" autoComplete="new-password" />
                <div className="strength-bar" aria-hidden>
                  {[1, 2, 3, 4].map(n => (
                    <div key={n} className={`strength-seg ${strength.score >= n ? `active-${Math.min(strength.score, 4)}` : ''}`} />
                  ))}
                </div>
                <div className="strength-label">
                  <span>{strength.label}</span>
                  <span>{password.length} chars</span>
                </div>
              </div>

              <button type="submit" className="btn btn-primary auth-submit btn-lg">Continue →</button>

              <div className="auth-terms">
                By creating an account you agree to our <a href="#">Terms</a> and <a href="#">Privacy Policy</a>.
              </div>
              <div className="auth-footer-link">
                Already have an account? <Link to="/login">Sign in</Link>
              </div>
            </form>
          )}

          {step === 2 && (
            <div className="animate-fade-up">
              <h1 className="auth-title">Which hat do you wear?</h1>
              <p className="auth-sub">We tune the scoping agent around your role. You can change this later.</p>

              <div className="role-grid">
                {ROLES.map(r => (
                  <button
                    key={r.label}
                    type="button"
                    className={`role-btn ${role === r.label ? 'active' : ''}`}
                    onClick={() => !submitting && completeSignup(r.label)}
                    disabled={submitting}
                  >
                    <span className="role-btn-label">{r.label}</span>
                    <span className="role-btn-desc">{r.desc}</span>
                  </button>
                ))}
              </div>

              <button type="button" onClick={() => setStep(1)} className="btn btn-ghost" style={{ marginTop: 8 }}>← Back</button>
              {submitting && <p style={{ fontSize: 13, color: 'var(--fg-dim)', marginTop: 18 }}>Creating your account…</p>}
            </div>
          )}

          {step === 3 && (
            <div className="success-card animate-fade-up">
              <div className="success-icon">
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12" /></svg>
              </div>
              <h1 className="auth-title" style={{ fontSize: 32 }}>Account created.</h1>
              <p className="auth-sub">
                Welcome, <strong style={{ color: 'var(--fg)' }}>{fullName}</strong>. Your workspace is ready — let's align your first project.
              </p>
              <button
                type="button"
                className="btn btn-primary auth-submit btn-lg"
                onClick={() => navigate('/dashboard')}
              >
                Go to dashboard →
              </button>
            </div>
          )}
        </div>
      </main>
    </div>
  );
};

export default SignupPage;
