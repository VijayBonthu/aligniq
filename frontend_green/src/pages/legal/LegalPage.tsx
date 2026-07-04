import React from 'react';
import { Link } from 'react-router-dom';
import { Logo } from '../../components/Logo';
import ThemeToggle from '../../components/layout/ThemeToggle';
import SiteFooter from '../../components/layout/SiteFooter';
import { usePageMeta } from '../../hooks/usePageMeta';

interface Props {
  title: string;
  /** Route path for canonical/og:url, e.g. "/security". */
  path: string;
  /** Page-specific meta description for SEO/social. */
  description?: string;
  /** Optional "Last updated" date — omit on evergreen marketing pages. */
  updated?: string;
  /** Custom footer note. Omit to get the default legal cross-link note (Terms/Privacy). */
  note?: React.ReactNode;
  children: React.ReactNode;
}

// Shared content-page shell (Terms, Privacy, About, Security, Careers, Changelog).
// Reuses the landing nav + container styling; prose styled by the `.legal*` block in
// globals.css. Legal pages get the default policy note; marketing pages pass their own.
// SEO title/description now come from src/seo/routes.mjs (keyed by `path`) — the
// `title` prop is the visible <h1>, and `description` is accepted for back-compat but
// no longer feeds meta (routes.mjs is the single source of truth).
const LegalPage: React.FC<Props> = ({ title, path, updated, note, children }) => {
  const isPrivacy = title.toLowerCase().includes('privacy');

  usePageMeta(path);

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

      <main className="legal">
        <div className="container">
          <article className="legal-doc">
            <h1 className="legal-title">{title}</h1>
            {updated && <div className="legal-updated">Last updated: {updated}</div>}
            {children}
            <div className="legal-note">
              {note ?? (
                <>
                  Questions about this policy? Email{' '}
                  <a href="mailto:hello@grounded-iq.com">hello@grounded-iq.com</a>. See also our{' '}
                  <Link to={isPrivacy ? '/terms' : '/privacy'}>
                    {isPrivacy ? 'Terms of Service' : 'Privacy Policy'}
                  </Link>.
                </>
              )}
            </div>
          </article>
        </div>
      </main>

      <SiteFooter />
    </div>
  );
};

export default LegalPage;
