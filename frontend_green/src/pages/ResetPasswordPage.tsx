import React, { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import toast from 'react-hot-toast';
import api from '../services/api';
import { AuthAside } from '../components/auth/AuthAside';
import { passwordStrength } from '../utils/passwordStrength';

const ResetPasswordPage: React.FC = () => {
  const [params] = useSearchParams();
  const token = params.get('token') || '';
  const navigate = useNavigate();

  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);

  const strength = passwordStrength(password);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    if (password.length < 8) return setError('Password must be at least 8 characters.');
    if (password !== confirm) return setError('Passwords do not match.');
    setSubmitting(true);
    try {
      await api.post('/auth/reset-password', { token, new_password: password });
      setDone(true);
      toast.success('Password updated.');
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'response' in err) {
        const axErr = err as { response?: { data?: { detail?: string } } };
        setError(axErr.response?.data?.detail || 'Could not reset your password.');
      } else setError('Something went wrong. Please try again.');
    } finally {
      setSubmitting(false);
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

          {done ? (
            <div className="success-card animate-fade-up">
              <div className="success-icon">
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12" /></svg>
              </div>
              <h1 className="auth-title" style={{ fontSize: 32 }}>Password updated.</h1>
              <p className="auth-sub">You can now sign in with your new password.</p>
              <button type="button" className="btn btn-primary auth-submit btn-lg" onClick={() => navigate('/login')}>
                Sign in →
              </button>
            </div>
          ) : !token ? (
            <div className="animate-fade-up">
              <div className="auth-eyebrow">Account recovery</div>
              <h1 className="auth-title">Link not valid.</h1>
              <p className="auth-sub">This reset link is missing or malformed. Request a fresh one from the sign-in page.</p>
              <Link to="/login" className="btn btn-primary auth-submit btn-lg" style={{ display: 'inline-flex', justifyContent: 'center' }}>
                Back to sign in →
              </Link>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="animate-fade-up">
              <div className="auth-eyebrow">Account recovery</div>
              <h1 className="auth-title">Set a new password.</h1>
              <p className="auth-sub">Choose a strong password you don't use anywhere else.</p>

              <div className="field">
                <label>New password</label>
                <input className="input" type="password" value={password} onChange={e => { setPassword(e.target.value); setError(''); }} placeholder="At least 8 characters" autoComplete="new-password" autoFocus />
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

              <div className="field">
                <label>Confirm password</label>
                <input className="input" type="password" value={confirm} onChange={e => { setConfirm(e.target.value); setError(''); }} placeholder="Re-enter your password" autoComplete="new-password" />
              </div>

              <button type="submit" disabled={submitting} className="btn btn-primary auth-submit btn-lg">
                {submitting ? 'Updating…' : 'Update password →'}
              </button>

              <div className="auth-footer-link">
                Remembered it? <Link to="/login">Back to sign in</Link>
              </div>
            </form>
          )}
        </div>
      </main>
    </div>
  );
};

export default ResetPasswordPage;
