import React from 'react';

// Brand glyphs for the social links. Inline SVG (no icon dependency) to match the
// hand-rolled icon set on the landing page. Used in the footer and on the contact page.
const X_PATH = 'M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z';
const LINKEDIN_PATH = 'M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 01-2.063-2.065 2.064 2.064 0 112.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.225 0z';

interface Props {
  x?: string;
  instagram?: string;
  linkedin?: string;
  /** icon box size in px */
  size?: number;
}

export const SocialIcons: React.FC<Props> = ({ x, instagram, linkedin, size = 20 }) => (
  <div className="social-icons">
    {x && (
      <a href={x} target="_blank" rel="noreferrer noopener" aria-label="GroundedIQ on X (Twitter)" title="X (Twitter)">
        <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden>
          <path d={X_PATH} />
        </svg>
      </a>
    )}
    {instagram && (
      <a href={instagram} target="_blank" rel="noreferrer noopener" aria-label="GroundedIQ on Instagram" title="Instagram">
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
          <rect x="2" y="2" width="20" height="20" rx="5" ry="5" />
          <path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z" />
          <line x1="17.5" y1="6.5" x2="17.51" y2="6.5" />
        </svg>
      </a>
    )}
    {linkedin && (
      <a href={linkedin} target="_blank" rel="noreferrer noopener" aria-label="GroundedIQ on LinkedIn" title="LinkedIn">
        <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden>
          <path d={LINKEDIN_PATH} />
        </svg>
      </a>
    )}
  </div>
);

export default SocialIcons;
