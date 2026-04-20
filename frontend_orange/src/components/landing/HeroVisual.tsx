import React from 'react';

export const HeroVisual: React.FC = () => {
  const gid = React.useId();
  return (
    <div className="hero-visual">
      <div className="hv-ring hv-ring-1" />
      <div className="hv-ring hv-ring-2" />
      <div className="hv-ring hv-ring-3" />

      <svg className="hv-lines" viewBox="0 0 400 400" aria-hidden>
        <defs>
          <linearGradient id={gid} x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="var(--accent)" stopOpacity="0" />
            <stop offset="50%" stopColor="var(--accent)" stopOpacity="0.6" />
            <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
          </linearGradient>
        </defs>
        <path d="M 60 80 Q 200 120 340 80" stroke={`url(#${gid})`} strokeWidth="1" fill="none" />
        <path d="M 60 320 Q 200 280 340 320" stroke={`url(#${gid})`} strokeWidth="1" fill="none" />
      </svg>

      <div className="hv-node hv-node-client">
        <div className="hv-node-label">Client</div>
        <div className="hv-node-body">Needs · Goals · Constraints</div>
      </div>

      <div className="hv-node hv-node-consult">
        <div className="hv-node-label">Consultant</div>
        <div className="hv-node-body">Architecture · Team · Plan</div>
      </div>

      <div className="hv-center">
        <div className="hv-center-inner">
          <div className="mono hv-center-label">ALIGNMENT</div>
          <div className="display hv-center-val">01</div>
        </div>
      </div>
    </div>
  );
};
