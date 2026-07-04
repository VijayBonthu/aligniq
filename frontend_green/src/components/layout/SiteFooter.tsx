import React from 'react';
import { Link } from 'react-router-dom';
import { Logo } from '../Logo';
import { SocialIcons } from '../SocialIcons';

const X_URL = 'https://x.com/GroundedIQ';
const INSTAGRAM_URL = 'https://www.instagram.com/groundediq';
const LINKEDIN_URL = 'https://www.linkedin.com/company/grounded-iq';

interface Props {
  /** Show the "Start free" CTA band above the footer. On for sub-pages (their
   *  conversion path); off on the landing page, which has its own CTA box. */
  cta?: boolean;
}

/**
 * Shared site footer — the internal-linking hub for the marketing site. Rendered on
 * every public page so each one links out to the full route set with crawlable
 * react-router <Link>s (previously only the landing page had a footer, leaving every
 * other page an orphan for crawlers and a dead-end for users). Homepage section
 * anchors use "/#id" so they resolve from any route; real pages use <Link>.
 */
const SiteFooter: React.FC<Props> = ({ cta = true }) => (
  <footer>
    <div className="container">
      {cta && (
        <div
          style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            flexWrap: 'wrap', gap: 20, padding: '40px 0 8px',
          }}
        >
          <span className="display" style={{ fontSize: 22 }}>
            Put your next engagement on solid ground.
          </span>
          <Link to="/signup" className="btn btn-primary btn-lg">Start free →</Link>
        </div>
      )}

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
            <a href="/#features">Features</a>
            <Link to="/pricing">Pricing</Link>
            <a href="/#how">How it works</a>
          </div>
          <div>
            <div className="footer-col-h">Company</div>
            <Link to="/about">About</Link>
            <Link to="/careers">Careers</Link>
            <Link to="/contact">Contact</Link>
          </div>
          <div>
            <div className="footer-col-h">Resources</div>
            <a href="/#faq">FAQ</a>
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
  </footer>
);

export default SiteFooter;
