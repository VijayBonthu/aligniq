import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { Logo } from '../components/Logo';
import ThemeToggle from '../components/layout/ThemeToggle';
import { HeroVisual } from '../components/landing/HeroVisual';
import { RealFlowTour } from '../components/landing/RealFlowTour';
import { Reveal } from '../components/landing/Reveal';
import { SocialIcons } from '../components/SocialIcons';
import { PLANS, PRO_CONTACT_EMAIL } from '../data/plans';
import { usePageMeta } from '../hooks/usePageMeta';
import { FAQS } from '../seo/routes.mjs';
import { LAUNCH_OFFER, LAUNCH_DISCOUNT_PCT, discountedPrice } from '../lib/launchOffer';

const X_URL = 'https://x.com/GroundedIQ';
const INSTAGRAM_URL = 'https://www.instagram.com/groundediq';
const LINKEDIN_URL = 'https://www.linkedin.com/company/grounded-iq';

// ── Small icon set ────────────────────────────────────────────────────────────
const Ico = {
  warn: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" /><line x1="12" y1="9" x2="12" y2="13" /><line x1="12" y1="17" x2="12.01" y2="17" /></svg>
  ),
  q: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10" /><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" /><line x1="12" y1="17" x2="12.01" y2="17" /></svg>
  ),
  arch: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="7" height="7" /><rect x="14" y="3" width="7" height="7" /><rect x="14" y="14" width="7" height="7" /><rect x="3" y="14" width="7" height="7" /></svg>
  ),
  clock: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" /></svg>
  ),
  people: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M23 21v-2a4 4 0 0 0-3-3.87" /><path d="M16 3.13a4 4 0 0 1 0 7.75" /></svg>
  ),
  doc: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" /><line x1="16" y1="13" x2="8" y2="13" /><line x1="16" y1="17" x2="8" y2="17" /></svg>
  ),
  check: (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12" /></svg>
  ),
};

const FEATURES = [
  { icon: Ico.warn,  title: 'Risk detection',         body: 'Every ambiguity surfaced before it becomes a $50k change order. HIGH/MED/LOW with mitigation.' },
  { icon: Ico.q,     title: 'Clarifying Q&A',         body: 'The questions your best architect would ask — auto-generated, with "why it matters" context.' },
  { icon: Ico.arch,  title: 'Architecture decisions', body: 'Stack, topology, integration style. First-pass recommendation grounded in the brief.' },
  { icon: Ico.clock, title: 'Timeline & phases',      body: 'Week-level phasing that accounts for the risks we just found. Not a Gantt guess.' },
  { icon: Ico.people,title: 'Resource plan',          body: 'Role allocation across phases. Tell ops who to staff before the kickoff call.' },
  { icon: Ico.doc,   title: 'Shared source of truth', body: 'One alignment report. Client and consultant read the same doc, sign the same assumptions.' },
];

const LandingPage: React.FC = () => {
  const [openFaq, setOpenFaq] = useState<number | null>(0);

  // Resets title/canonical/og/description from routes.mjs when navigating back to "/".
  // The same source feeds the FAQPage structured data baked into the homepage HTML.
  usePageMeta('/');

  return (
    <div>
      {/* ─── Nav ─── */}
      <nav className="nav">
        <div className="container nav-inner">
          <Link to="/"><Logo /></Link>
          <div className="nav-links">
            <a href="#how">How it works</a>
            <a href="#features">Features</a>
            <a href="#pricing">Pricing</a>
            <a href="#faq">FAQ</a>
          </div>
          <div className="nav-cta">
            <ThemeToggle size={38} />
            <Link to="/login" className="btn btn-ghost">Sign in</Link>
            <Link to="/signup" className="btn btn-primary">Start scoping →</Link>
          </div>
        </div>
      </nav>

      {/* ─── Hero ─── */}
      <section className="hero">
        <div className="container">
          <div className="hero-split">
            <div className="hero-copy">
              <div className="eyebrow hero-eyebrow">
                <span className="dot-live" /> Evidence-grounded scoping for consulting teams
              </div>
              <h1 className="display hero-title">
                Every estimate, <i>grounded</i> in the brief.
              </h1>
              <p className="hero-sub">
                GroundedIQ reads a raw brief like your sharpest architect — surfacing the buried risks, raising the questions that move the estimate, and grounding every assumption in evidence. The alignment report your client signs before a line of code is written.
              </p>
              <div className="hero-cta">
                <Link to="/signup" className="btn btn-primary btn-lg">Scope a brief, free →</Link>
                <a href="#how" className="btn btn-ghost btn-lg">Watch it work</a>
              </div>
              <div className="hero-stats">
                <div>
                  <div className="hero-stat-v">2 min</div>
                  <div className="hero-stat-l">To a first readiness score</div>
                </div>
                <div>
                  <div className="hero-stat-v">100%</div>
                  <div className="hero-stat-l">Assumptions traced to the brief</div>
                </div>
                <div>
                  <div className="hero-stat-v">1 doc</div>
                  <div className="hero-stat-l">Client &amp; team sign the same truth</div>
                </div>
              </div>
            </div>
            <HeroVisual />
          </div>
        </div>
      </section>

      {/* ─── Real-flow tour (replaces the old how-it-works + demo + sample mockups) ─── */}
      <RealFlowTour />

      {/* ─── Features ─── */}
      <section id="features" className="section">
        <div className="container">
          <Reveal>
            <div className="eyebrow section-eyebrow">Capabilities</div>
            <h2 className="display section-h">Six capabilities. One grounded source of truth.</h2>
          </Reveal>
          <Reveal delay={80}>
            <div className="feature-grid">
              {FEATURES.map(f => (
                <div key={f.title} className="feature">
                  <div className="feature-icon">{f.icon}</div>
                  <div className="feature-title">{f.title}</div>
                  <div className="feature-body">{f.body}</div>
                </div>
              ))}
            </div>
          </Reveal>
        </div>
      </section>

      {/* ─── Pricing ─── */}
      <section id="pricing" className="section">
        <div className="container">
          <Reveal>
            <div className="eyebrow section-eyebrow">Pricing</div>
            <h2 className="display section-h">Priced to scope your whole pipeline.</h2>
            {LAUNCH_OFFER && (
              <p className="section-sub" style={{ margin: '8px 0 0', color: 'var(--accent)', fontWeight: 500 }}>
                🎉 Launch offer — {LAUNCH_DISCOUNT_PCT}% off your first 2 months on Basic &amp; Plus for new subscribers.
              </p>
            )}
          </Reveal>
          <Reveal delay={80}>
            <div className="tiers">
              {PLANS.map(plan => {
                const ctaTo =
                  plan.ctaKind === 'contact'
                    ? `mailto:${PRO_CONTACT_EMAIL}?subject=GroundedIQ Pro Plan`
                    : plan.ctaKind === 'free'
                    ? '/signup'
                    : `/signup?intent=upgrade&tier=${plan.id}`;
                const isExternal = plan.ctaKind === 'contact';
                const btnClass = plan.highlight ? 'btn btn-primary' : 'btn btn-ghost';
                const periodLabel = plan.period ? plan.period.replace(/^\//, '/ ') : '';
                return (
                  <div key={plan.id} className={`tier${plan.highlight ? ' featured' : ''}`}>
                    {plan.highlight && <div className="tier-badge">MOST POPULAR</div>}
                    <div className="tier-name display">{plan.name}</div>
                    <div className="tier-price-row">
                      {LAUNCH_OFFER && plan.ctaKind === 'checkout' ? (
                        <>
                          <span
                            className="display tier-price"
                            style={{ textDecoration: 'line-through', opacity: 0.45, fontSize: '0.62em', marginRight: 8 }}
                          >
                            {plan.price}
                          </span>
                          <span className="display tier-price">{discountedPrice(plan.price)}</span>
                          {periodLabel && <span className="tier-per">{periodLabel}</span>}
                        </>
                      ) : (
                        <>
                          <span className="display tier-price">{plan.price}</span>
                          {periodLabel && <span className="tier-per">{periodLabel}</span>}
                        </>
                      )}
                    </div>
                    {LAUNCH_OFFER && plan.ctaKind === 'checkout' && (
                      <div style={{ fontSize: 11.5, color: 'var(--accent)', fontWeight: 500, marginTop: 2 }}>
                        {LAUNCH_DISCOUNT_PCT}% off · first 2 months, then {plan.price}{periodLabel}
                      </div>
                    )}
                    <div className="tier-sub">{plan.description}</div>
                    <div className="tier-sep" />
                    <ul className="tier-feats">
                      {plan.features.map(f => (
                        <li key={f}>{Ico.check}<span>{f}</span></li>
                      ))}
                    </ul>
                    {isExternal ? (
                      <a href={ctaTo} className={btnClass} style={{ width: '100%' }}>
                        {plan.ctaLabel}
                      </a>
                    ) : (
                      <Link to={ctaTo} className={btnClass} style={{ width: '100%' }}>
                        {plan.ctaLabel}
                      </Link>
                    )}
                  </div>
                );
              })}
            </div>
          </Reveal>
          <p style={{ textAlign: 'center', marginTop: 28, fontSize: 13, color: 'var(--fg-dim)' }}>
            Already have an account? <Link to="/pricing" style={{ color: 'var(--accent)' }}>View detailed plans →</Link>
          </p>
        </div>
      </section>

      {/* ─── FAQ ─── */}
      <section id="faq" className="section">
        <div className="container">
          <div className="faq-grid">
            <Reveal variant="left">
              <div className="eyebrow section-eyebrow">FAQ</div>
              <h2 className="display section-h">Questions teams actually ask us.</h2>
              <p className="section-sub" style={{ margin: 0 }}>
                Can't find it? <Link to="/contact" style={{ color: 'var(--accent)' }}>Ask the team →</Link>
              </p>
            </Reveal>
            <div className="faq-list">
              {FAQS.map((f, i) => (
                <div key={i} className="faq-item">
                  <button className="faq-q" onClick={() => setOpenFaq(openFaq === i ? null : i)}>
                    <span>{f.q}</span>
                    <span className="faq-tog">{openFaq === i ? '−' : '+'}</span>
                  </button>
                  {openFaq === i && <div className="faq-a animate-fade-up">{f.a}</div>}
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ─── CTA + Footer ─── */}
      <section className="cta-footer">
        <div className="container">
          <Reveal className="cta-box">
            <div className="eyebrow">Ready</div>
            <h2 className="display cta-title">Put your next engagement on solid ground.</h2>
            <p className="cta-sub">Free forever plan. No credit card. Your first grounded scope in under a minute.</p>
            <div className="hero-cta">
              <Link to="/signup" className="btn btn-primary btn-lg">Create free account →</Link>
              <a href="#how" className="btn btn-ghost btn-lg">See how it works</a>
            </div>
          </Reveal>

          <div className="footer">
            <div>
              <Logo />
              <div className="footer-tag">Grounded scoping, before kickoff.</div>
              <div className="footer-social">
                <SocialIcons x={X_URL} instagram={INSTAGRAM_URL} linkedin={LINKEDIN_URL} />
              </div>
            </div>
            <div className="footer-cols">
              <div>
                <div className="footer-col-h">Product</div>
                <a href="#features">Features</a>
                <a href="#pricing">Pricing</a>
                <a href="#how">How it works</a>
              </div>
              <div>
                <div className="footer-col-h">Company</div>
                <Link to="/about">About</Link>
                <Link to="/careers">Careers</Link>
                <Link to="/contact">Contact</Link>
              </div>
              <div>
                <div className="footer-col-h">Resources</div>
                <a href="#faq">FAQ</a>
                <Link to="/changelog">Changelog</Link>
                <Link to="/security">Security</Link>
              </div>
            </div>
          </div>

          <div className="footer-bottom">
            <span>© 2026 GroundedIQ, Inc.</span>
            <span style={{ display: 'flex', gap: 18 }}>
              <Link to="/privacy">Privacy</Link>
              <Link to="/terms">Terms</Link>
            </span>
          </div>
        </div>
      </section>
    </div>
  );
};

export default LandingPage;
