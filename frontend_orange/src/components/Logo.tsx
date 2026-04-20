import React from 'react';

export const Logo: React.FC<{ size?: number; wordmark?: boolean }> = ({ size = 26, wordmark = true }) => {
  const gid = React.useId();
  return (
    <span className="logo">
      <span style={{ width: size, height: size, display: 'inline-block', position: 'relative' }}>
        <svg viewBox="0 0 32 32" width={size} height={size} fill="none" aria-hidden>
          <defs>
            <linearGradient id={gid} x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stopColor="var(--accent)" />
              <stop offset="100%" stopColor="var(--accent-2)" />
            </linearGradient>
          </defs>
          <path d="M4 22 Q 4 6 16 6" stroke={`url(#${gid})`} strokeWidth="2" strokeLinecap="round" />
          <path d="M28 22 Q 28 6 16 6" stroke={`url(#${gid})`} strokeWidth="2" strokeLinecap="round" opacity="0.6" />
          <circle cx="16" cy="6" r="2.6" fill="var(--accent)" />
          <line x1="4" y1="26" x2="28" y2="26" stroke="currentColor" strokeWidth="1" opacity="0.35" />
        </svg>
      </span>
      {wordmark && (
        <span>
          Align<i>IQ</i>
        </span>
      )}
    </span>
  );
};
