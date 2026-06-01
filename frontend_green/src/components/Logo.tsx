import React from 'react';

export const Logo: React.FC<{ size?: number; wordmark?: boolean }> = ({ size = 26, wordmark = true }) => {
  return (
    <span className="logo">
      <span style={{ width: size, height: size, display: 'inline-block', position: 'relative' }}>
        {/* GroundedIQ surveyor's mark — calibrated horizon + plumb stem + intelligence dot */}
        <svg viewBox="0 0 32 32" width={size} height={size} fill="none" aria-hidden>
          <line x1="4" y1="19" x2="4" y2="25" stroke="currentColor" strokeWidth="1" opacity="0.4" />
          <line x1="28" y1="19" x2="28" y2="25" stroke="currentColor" strokeWidth="1" opacity="0.4" />
          <line x1="4" y1="22" x2="28" y2="22" stroke="var(--accent)" strokeWidth="2" strokeLinecap="round" />
          <line x1="16" y1="22" x2="16" y2="11" stroke="var(--accent)" strokeWidth="2" strokeLinecap="round" />
          <circle cx="16" cy="7.5" r="3" fill="var(--accent)" />
        </svg>
      </span>
      {wordmark && (
        <span>
          Grounded<i>IQ</i>
        </span>
      )}
    </span>
  );
};
