import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { Logo } from '../components/Logo';
import { HeroVisual } from '../components/landing/HeroVisual';
import { Demo } from '../components/landing/Demo';
import { TypingHeadline } from '../components/landing/TypingHeadline';

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

const FAQS = [
  { q: 'How is this different from an RFP tool?',
    a: 'RFP tools capture requirements. AlignIQ interrogates them — it flags ambiguity, proposes architecture, and produces a doc clients actually sign off on before kickoff.' },
  { q: 'Does it replace discovery workshops?',
    a: 'No. It kills 80% of the "what did you mean by X" questions so your discovery time is spent on judgment calls, not information gathering.' },
  { q: 'What does the output look like?',
    a: 'A structured alignment report: risks ranked by severity, clarifying questions, a first-pass architecture, week-level phasing, and a resource plan. All Markdown-exportable.' },
  { q: 'Can I bring my own LLM?',
    a: 'On the Team and Enterprise tiers, yes — OpenAI, Anthropic, or Azure OpenAI. Starter uses our shared inference.' },
  { q: 'Is my client data used for training?',
    a: 'No. Inputs are processed ephemerally and are not used to train any models. SOC 2 Type II, GDPR, ISO 27001.' },
];

const LandingPage: React.FC = () => {
  const [openFaq, setOpenFaq] = useState<number | null>(0);

  return (
    <div>
      {/* ─── Nav ─── */}
      <nav className="nav">
        <div className="container nav-inner">
          <Link to="/"><Logo /></Link>
          <div className="nav-links">
            <a href="#how">How it works</a>
            <a href="#demo">Live demo</a>
            <a href="#features">Features</a>
            <a href="#pricing">Pricing</a>
            <a href="#faq">FAQ</a>
          </div>
          <div className="nav-cta">
            <Link to="/login" className="btn btn-ghost">Sign in</Link>
            <Link to="/signup" className="btn btn-primary">Start aligning →</Link>
          </div>
        </div>
      </nav>

      {/* ─── Hero ─── */}
      <section className="hero">
        <div className="container">
          <div className="hero-split">
            <div>
              <div className="eyebrow hero-eyebrow">
                <span className="dot-live" /> AI scoping · launched for consulting teams
              </div>
              <h1 className="display hero-title">
                Every project, <i>aligned</i> from day one.
              </h1>
              <p className="hero-sub">
                AlignIQ interrogates the brief the way your best architect would — surfacing risk, asking the right questions, and producing the report your client actually reads before kickoff.
              </p>
              <div className="hero-cta">
                <Link to="/signup" className="btn btn-primary btn-lg">Start a scope →</Link>
                <a href="#demo" className="btn btn-ghost btn-lg">See it work</a>
              </div>
              <div className="hero-stats">
                <div>
                  <div className="hero-stat-v">−68%</div>
                  <div className="hero-stat-l">Scope creep</div>
                </div>
                <div>
                  <div className="hero-stat-v">3.2w</div>
                  <div className="hero-stat-l">Saved per project</div>
                </div>
                <div>
                  <div className="hero-stat-v">96%</div>
                  <div className="hero-stat-l">Client alignment</div>
                </div>
              </div>
            </div>
            <HeroVisual />
          </div>
        </div>
      </section>

      {/* ─── How It Works ─── */}
      <section id="how" className="section">
        <div className="container">
          <div className="eyebrow section-eyebrow">How it works</div>
          <h2 className="display section-h">From fuzzy brief to aligned plan in under a minute.</h2>
          <div className="steps">
            <div className="step"><div className="mono step-n">01</div><div className="step-title">Drop in the brief</div><div className="step-body">Paste an RFP, Slack thread, discovery notes, or upload a doc. Any fidelity.</div></div>
            <div className="step"><div className="mono step-n">02</div><div className="step-title">AlignIQ interrogates</div><div className="step-body">Nine agents scan for ambiguity, risks, feasibility gaps, and hidden assumptions.</div></div>
            <div className="step"><div className="mono step-n">03</div><div className="step-title">You answer what matters</div><div className="step-body">A tight set of P1 blockers. Kickstart questions. Apply assumptions for the rest.</div></div>
            <div className="step"><div className="mono step-n">04</div><div className="step-title">Ship the alignment doc</div><div className="step-body">Risks, arch, timeline, and resources — in one report the client signs off on.</div></div>
          </div>
        </div>
      </section>

      {/* ─── Demo ─── */}
      <section id="demo" className="section" style={{ paddingTop: 60 }}>
        <div className="container">
          <div className="eyebrow section-eyebrow">Live demo</div>
          <h2 className="display section-h">Try it on a real brief.</h2>
          <Demo />
        </div>
      </section>

      {/* ─── Features ─── */}
      <section id="features" className="section">
        <div className="container">
          <div className="eyebrow section-eyebrow">Capabilities</div>
          <h2 className="display section-h">Six capabilities. One shared understanding.</h2>
          <div className="feature-grid">
            {FEATURES.map(f => (
              <div key={f.title} className="feature">
                <div className="feature-icon">{f.icon}</div>
                <div className="feature-title">{f.title}</div>
                <div className="feature-body">{f.body}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ─── Sample report ─── */}
      <section className="section" style={{ paddingTop: 40 }}>
        <div className="container">
          <div className="eyebrow section-eyebrow">The output</div>
          <TypingHeadline prefix="Every brief rewritten as " suffix="a report you can send to the client." />
          <div className="report-frame" style={{ marginTop: 40 }}>
            <div className="report-chrome">
              <div className="report-chrome-dots"><span /><span /><span /></div>
              <span>alignIQ / logistics-platform.md</span>
            </div>
            <div className="report-body">
              <div className="report-sidebar">
                <div className="report-sb-item">Executive summary</div>
                <div className="report-sb-item active">Identified risks</div>
                <div className="report-sb-item">Clarifying questions</div>
                <div className="report-sb-item">Architecture</div>
                <div className="report-sb-item">Phasing & timeline</div>
                <div className="report-sb-item">Resource plan</div>
                <div className="report-sb-item">Assumptions</div>
              </div>
              <div className="report-content">
                <h3 className="report-h">Identified risks</h3>
                <div className="report-risk">
                  <div className="report-risk-head">
                    <span className="demo-sev demo-sev-high">HIGH</span>
                    <div className="report-risk-title">Data residency is unspecified but EU + US customers are in-scope.</div>
                  </div>
                  <div className="report-risk-mit">
                    <span className="report-risk-mit-label">Mitigation</span>
                    <span>Confirm region strategy (single-region vs active-active) before architecture sign-off.</span>
                  </div>
                </div>
                <div className="report-risk">
                  <div className="report-risk-head">
                    <span className="demo-sev demo-sev-med">MED</span>
                    <div className="report-risk-title">SAP integration style not specified — read-only vs bidirectional sync.</div>
                  </div>
                  <div className="report-risk-mit">
                    <span className="report-risk-mit-label">Mitigation</span>
                    <span>Add 2-week SAP discovery spike to W1. Assume read-only until confirmed.</span>
                  </div>
                </div>
                <div className="report-risk">
                  <div className="report-risk-head">
                    <span className="demo-sev demo-sev-med">MED</span>
                    <div className="report-risk-title">Q2 launch is tight for full scope. Phasing recommended.</div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ─── Social proof ─── */}
      <section id="proof" className="proof">
        <div className="container">
          <div className="proof-logos">
            {['Kaleido', 'Northfield', 'Helix&Co', 'Rowan', 'Aperture', 'Veridian', 'Archway'].map(n => (
              <span key={n} className="proof-logo">{n}</span>
            ))}
          </div>
          <div className="proof-quotes">
            <div className="quote">
              <div className="quote-mark">"</div>
              <div className="quote-body">Our kickoffs used to run 4 weeks. Now we walk into week one with the arch decisions already written down.</div>
              <div className="quote-author">Mira Okafor</div>
              <div className="quote-role">VP Engineering · Kaleido Consulting</div>
            </div>
            <div className="quote">
              <div className="quote-mark">"</div>
              <div className="quote-body">It asks the questions I would have asked. I get to spend discovery on judgment, not scavenger hunts.</div>
              <div className="quote-author">David Aminoff</div>
              <div className="quote-role">Principal Architect · Northfield Digital</div>
            </div>
          </div>
        </div>
      </section>

      {/* ─── Pricing ─── */}
      <section id="pricing" className="section">
        <div className="container">
          <div className="eyebrow section-eyebrow">Pricing</div>
          <h2 className="display section-h">Priced per seat, not per word.</h2>
          <div className="tiers">
            <div className="tier">
              <div className="tier-name display">Starter</div>
              <div className="tier-price-row"><span className="display tier-price">$0</span><span className="tier-per">/ forever</span></div>
              <div className="tier-sub">Solo consultants. Students. Tire-kickers.</div>
              <div className="tier-sep" />
              <ul className="tier-feats">
                <li>{Ico.check}<span>3 scoping reports / mo</span></li>
                <li>{Ico.check}<span>Core 9-agent pipeline</span></li>
                <li>{Ico.check}<span>Markdown export</span></li>
                <li>{Ico.check}<span>Community support</span></li>
              </ul>
              <Link to="/signup" className="btn btn-ghost" style={{ width: '100%' }}>Start free</Link>
            </div>

            <div className="tier featured">
              <div className="tier-badge">MOST POPULAR</div>
              <div className="tier-name display">Team</div>
              <div className="tier-price-row"><span className="display tier-price">$49</span><span className="tier-per">/ seat / mo</span></div>
              <div className="tier-sub">Consulting practices. Boutique studios.</div>
              <div className="tier-sep" />
              <ul className="tier-feats">
                <li>{Ico.check}<span>Unlimited reports</span></li>
                <li>{Ico.check}<span>Shared workspace + version history</span></li>
                <li>{Ico.check}<span>Jira / Linear / Notion export</span></li>
                <li>{Ico.check}<span>Bring-your-own-LLM</span></li>
                <li>{Ico.check}<span>Priority support</span></li>
              </ul>
              <Link to="/signup" className="btn btn-primary" style={{ width: '100%' }}>Start 14-day trial</Link>
            </div>

            <div className="tier">
              <div className="tier-name display">Enterprise</div>
              <div className="tier-price-row"><span className="display tier-price">Custom</span></div>
              <div className="tier-sub">Large consultancies. Regulated industries.</div>
              <div className="tier-sep" />
              <ul className="tier-feats">
                <li>{Ico.check}<span>Everything in Team</span></li>
                <li>{Ico.check}<span>SSO (SAML / OIDC)</span></li>
                <li>{Ico.check}<span>Private cloud deploy</span></li>
                <li>{Ico.check}<span>SOC 2, GDPR, ISO 27001 addenda</span></li>
                <li>{Ico.check}<span>Named success manager</span></li>
              </ul>
              <a href="mailto:sales@aligniq.io" className="btn btn-ghost" style={{ width: '100%' }}>Talk to sales</a>
            </div>
          </div>
        </div>
      </section>

      {/* ─── FAQ ─── */}
      <section id="faq" className="section">
        <div className="container">
          <div className="faq-grid">
            <div>
              <div className="eyebrow section-eyebrow">FAQ</div>
              <h2 className="display section-h">Questions teams actually ask us.</h2>
              <p className="section-sub" style={{ margin: 0 }}>
                Can't find it? <a href="mailto:hello@aligniq.io" style={{ color: 'var(--accent)' }}>Ask the team →</a>
              </p>
            </div>
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
          <div className="cta-box">
            <div className="eyebrow">Ready</div>
            <h2 className="display cta-title">Start the next project aligned.</h2>
            <p className="cta-sub">Free forever plan. No credit card. Your first scope report in under a minute.</p>
            <div className="hero-cta">
              <Link to="/signup" className="btn btn-primary btn-lg">Create free account →</Link>
              <a href="#demo" className="btn btn-ghost btn-lg">Try the demo</a>
            </div>
          </div>

          <div className="footer">
            <div>
              <Logo />
              <div className="footer-tag">Alignment, before kickoff.</div>
            </div>
            <div className="footer-cols">
              <div>
                <div className="footer-col-h">Product</div>
                <a href="#features">Features</a>
                <a href="#pricing">Pricing</a>
                <a href="#demo">Live demo</a>
              </div>
              <div>
                <div className="footer-col-h">Company</div>
                <a href="#">About</a>
                <a href="#">Careers</a>
                <a href="mailto:hello@aligniq.io">Contact</a>
              </div>
              <div>
                <div className="footer-col-h">Resources</div>
                <a href="#faq">FAQ</a>
                <a href="#">Changelog</a>
                <a href="#">Security</a>
              </div>
            </div>
          </div>

          <div className="footer-bottom">
            <span>© 2026 AlignIQ, Inc.</span>
            <span>SOC 2 Type II · GDPR · ISO 27001</span>
          </div>
        </div>
      </section>
    </div>
  );
};

export default LandingPage;
