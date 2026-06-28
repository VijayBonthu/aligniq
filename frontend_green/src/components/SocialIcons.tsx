import React from 'react';

// Brand glyphs for the social links. Inline SVG (no icon dependency) to match the
// hand-rolled icon set on the landing page. Used in the footer and on the contact page.
const X_PATH = 'M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z';

interface Props {
  x?: string;
  instagram?: string;
  /** icon box size in px */
  size?: number;
}

export const SocialIcons: React.FC<Props> = ({ x, instagram, size = 20 }) => (
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
  </div>
);

export default SocialIcons;
