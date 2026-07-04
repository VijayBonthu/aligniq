import React, { useState, type CSSProperties } from 'react';
import { Link } from 'react-router-dom';
import { usePageMeta } from '../hooks/usePageMeta';
import { toast } from 'react-hot-toast';
import { Logo } from '../components/Logo';
import ThemeToggle from '../components/layout/ThemeToggle';
import { TurnstileWidget } from '../components/auth/TurnstileWidget';
import { submitPublicContact, type ContactTopic } from '../services/supportService';
import { notifyError } from '../services/api';
import { SocialIcons } from '../components/SocialIcons';
import SiteFooter from '../components/layout/SiteFooter';
import { track } from '../lib/analytics';

const TURNSTILE_ENABLED = !!import.meta.env.VITE_TURNSTILE_SITE_KEY;

const SUPPORT_EMAIL = 'support@grounded-iq.com';
const SALES_EMAIL = 'hello@grounded-iq.com';
const X_URL = 'https://x.com/GroundedIQ';
const INSTAGRAM_URL = 'https://www.instagram.com/groundediq';
const LINKEDIN_URL = 'https://www.linkedin.com/company/grounded-iq';

const TOPICS: { value: ContactTopic; label: string }[] = [
  { value: 'general', label: 'General question' },
  { value: 'sales', label: 'Sales & pricing' },
  { value: 'account', label: 'Account & login help' },
  { value: 'bug', label: 'Bug report' },
];

const field: CSSProperties = {
  width: '100%',
  boxSizing: 'border-box',
  padding: '11px 13px',
  background: 'var(--bg)',
  border: '1px solid var(--border-strong)',
  borderRadius: 'var(--radius)',
  color: 'var(--fg)',
  fontSize: 14,
  fontFamily: 'var(--font-sans)',
  outline: 'none',
};

const label: CSSProperties = {
  display: 'block',
  fontSize: 12,
  color: 'var(--fg-dim)',
  marginBottom: 7,
  fontWeight: 500,
};

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

const ContactPage: React.FC = () => {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [topic, setTopic] = useState<ContactTopic>('general');
  const [message, setMessage] = useState('');
  const [honeypot, setHoneypot] = useState(''); // bots fill this; humans never see it
  const [turnstileToken, setTurnstileToken] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [doneRef, setDoneRef] = useState<string | null>(null);

  usePageMeta('/contact');

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (submitting) return;
    if (!name.trim()) return toast.error('Please tell us your name.');
    if (!EMAIL_RE.test(email.trim())) return toast.error('Please enter a valid email address.');
    if (!message.trim()) return toast.error('Please add a message.');
    if (TURNSTILE_ENABLED && !turnstileToken) return toast.error('Please complete the verification below.');

    setSubmitting(true);
    try {
      const res = await submitPublicContact({
        name: name.trim(),
        email: email.trim(),
        topic,
        message: message.trim(),
        turnstileToken: turnstileToken || undefined,
        honeypot,
      });
      setDoneRef(res.ref_code);
      track('Contact Submitted', { topic });
    } catch (err) {
      notifyError(err, 'Could not send your message. Please try again.');
    } finally {
      setSubmitting(false);
    }
  }

  const canSubmit = !!name.trim() && EMAIL_RE.test(email.trim()) && !!message.trim() && !submitting;

  return (
    <div>
      <nav className="nav">
        <div className="container nav-inner">
          <Link to="/"><Logo /></Link>
          <div className="nav-cta">
            <ThemeToggle size={38} />
            <Link to="/" className="btn btn-ghost">← Home</Link>
          </div>
        </div>
      </nav>

      <main className="section">
        <div className="container">
          <div className="eyebrow section-eyebrow">Contact</div>
          <h1 className="display section-h" style={{ marginBottom: 10 }}>Get in touch.</h1>
          <p className="section-sub" style={{ maxWidth: 620, marginTop: 0 }}>
            Questions about the product, pricing, your account, or just stuck? Send us a note and a
            real person replies — usually within one business day.
          </p>

          <div className="contact-grid">
            {/* ── Form / success ── */}
            <div className="contact-card">
              {doneRef ? (
                <div style={{ textAlign: 'center', padding: '18px 6px' }}>
                  <div
                    style={{
                      width: 50, height: 50, borderRadius: '50%', margin: '0 auto 16px',
                      background: 'var(--accent-soft)', border: '1px solid rgba(52,163,123,.3)',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                    }}
                  >
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                      <path d="M20 6 9 17l-5-5" />
                    </svg>
                  </div>
                  <h2 className="display" style={{ fontSize: 22, margin: '0 0 8px', color: 'var(--fg)' }}>
                    Thanks — message sent.
                  </h2>
                  <p style={{ fontSize: 14, color: 'var(--fg-dim)', margin: '0 0 6px', lineHeight: 1.6 }}>
                    We'll reply to <strong style={{ color: 'var(--fg)' }}>{email.trim()}</strong>.
                  </p>
                  <p style={{ fontSize: 13, color: 'var(--fg-muted)', margin: '0 0 22px', fontFamily: 'var(--font-mono)' }}>
                    Reference <span style={{ color: 'var(--accent)' }}>{doneRef}</span>
                  </p>
                  <div style={{ display: 'flex', gap: 10, justifyContent: 'center', flexWrap: 'wrap' }}>
                    <button
                      type="button"
                      className="btn btn-ghost"
                      onClick={() => { setDoneRef(null); setMessage(''); setTurnstileToken(''); }}
                    >
                      Send another
                    </button>
                    <Link to="/" className="btn btn-primary">Back to home</Link>
                  </div>
                </div>
              ) : (
                <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
                  {/* Honeypot — visually hidden, off the tab order; real users never fill it. */}
                  <div aria-hidden="true" style={{ position: 'absolute', left: '-9999px', width: 1, height: 1, overflow: 'hidden' }}>
                    <label htmlFor="contact-company">Company</label>
                    <input
                      id="contact-company"
                      type="text"
                      tabIndex={-1}
                      autoComplete="off"
                      value={honeypot}
                      onChange={e => setHoneypot(e.target.value)}
                    />
                  </div>

                  <div>
                    <span style={label}>What's this about?</span>
                    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                      {TOPICS.map(t => {
                        const active = topic === t.value;
                        return (
                          <button
                            key={t.value}
                            type="button"
                            onClick={() => setTopic(t.value)}
                            style={{
                              padding: '7px 13px',
                              borderRadius: 999,
                              fontSize: 12.5,
                              fontFamily: 'var(--font-sans)',
                              cursor: 'pointer',
                              transition: 'all .15s',
                              background: active ? 'var(--accent-soft)' : 'transparent',
                              border: `1px solid ${active ? 'var(--accent)' : 'var(--border-strong)'}`,
                              color: active ? 'var(--fg)' : 'var(--fg-dim)',
                            }}
                          >
                            {t.label}
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                    <div>
                      <label htmlFor="contact-name" style={label}>Your name</label>
                      <input id="contact-name" type="text" value={name} maxLength={120}
                        onChange={e => setName(e.target.value)} placeholder="Ada Lovelace"
                        autoComplete="name" style={field} />
                    </div>
                    <div>
                      <label htmlFor="contact-email" style={label}>Email</label>
                      <input id="contact-email" type="email" value={email} maxLength={254}
                        onChange={e => setEmail(e.target.value)} placeholder="you@company.com"
                        autoComplete="email" style={field} />
                    </div>
                  </div>

                  <div>
                    <label htmlFor="contact-message" style={label}>Message</label>
                    <textarea id="contact-message" value={message} maxLength={5000}
                      onChange={e => setMessage(e.target.value)}
                      placeholder="How can we help?"
                      rows={6} style={{ ...field, resize: 'vertical', minHeight: 120, lineHeight: 1.5 }} />
                  </div>

                  <TurnstileWidget onVerify={setTurnstileToken} onExpire={() => setTurnstileToken('')} />

                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
                    <p style={{ fontSize: 12, color: 'var(--fg-muted)', margin: 0 }}>
                      We never share your email.
                    </p>
                    <button type="submit" className="btn btn-primary" disabled={!canSubmit}>
                      {submitting ? 'Sending…' : 'Send message →'}
                    </button>
                  </div>
                </form>
              )}
            </div>

            {/* ── Other ways to reach us ── */}
            <aside className="contact-aside">
              <div className="contact-channel">
                <div className="contact-channel-h">Email us directly</div>
                <a href={`mailto:${SUPPORT_EMAIL}`}>{SUPPORT_EMAIL}</a>
                <span className="contact-channel-note">Support &amp; account help</span>
                <a href={`mailto:${SALES_EMAIL}`} style={{ marginTop: 10 }}>{SALES_EMAIL}</a>
                <span className="contact-channel-note">General &amp; sales enquiries</span>
              </div>

              <div className="contact-channel">
                <div className="contact-channel-h">Follow us</div>
                <SocialIcons x={X_URL} instagram={INSTAGRAM_URL} linkedin={LINKEDIN_URL} />
              </div>

              <div className="contact-channel">
                <div className="contact-channel-h">Can't access your account?</div>
                <span className="contact-channel-note" style={{ marginBottom: 8 }}>
                  Locked out or forgot your password? You don't need to log in to reach us.
                </span>
                <Link to="/reset-password">Reset your password →</Link>
                <Link to="/login" style={{ marginTop: 6 }}>Back to sign in →</Link>
              </div>
            </aside>
          </div>
        </div>
      </main>

      <SiteFooter cta={false} />
    </div>
  );
};

export default ContactPage;
