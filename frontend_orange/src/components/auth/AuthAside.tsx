import React from 'react';
import { Link } from 'react-router-dom';
import { Logo } from '../Logo';

export const AuthAside: React.FC = () => (
  <aside className="auth-side">
    <div className="auth-side-bg" aria-hidden />

    <div className="auth-side-top">
      <Link to="/"><Logo /></Link>
    </div>

    <div className="auth-side-mid">
      <h2 className="auth-quote">
        "Finally, a kickoff where everyone <i>starts on the same page.</i>"
      </h2>
      <div className="auth-quote-attr">
        — Mira Okafor, VP Eng, Kaleido Consulting
      </div>

      <div className="auth-preview">
        <div className="auth-preview-head">
          <span>alignIQ / sample scope</span>
          <span>0.24s</span>
        </div>
        <div className="auth-preview-row">
          <span className="auth-preview-sev high">HIGH</span>
          <div className="auth-preview-body">Data residency unclear — EU + US customers mentioned, no region plan.</div>
        </div>
        <div className="auth-preview-row">
          <span className="auth-preview-sev med">MED</span>
          <div className="auth-preview-body">Mobile scope ambiguous — native, hybrid, or responsive?</div>
        </div>
        <div className="auth-preview-row">
          <span className="auth-preview-sev q">Q</span>
          <div className="auth-preview-body">Confirm SLA target: 99.9% or 99.99% uptime?</div>
        </div>
      </div>
    </div>

    <div className="auth-meta">
      <span>© 2026 AlignIQ</span>
      <span>SOC 2 · GDPR · ISO 27001</span>
    </div>
  </aside>
);
