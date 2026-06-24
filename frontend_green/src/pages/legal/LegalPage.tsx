import React, { useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Logo } from '../../components/Logo';
import ThemeToggle from '../../components/layout/ThemeToggle';

interface Props {
  title: string;
  updated: string;
  children: React.ReactNode;
}

// Shared shell for the static legal pages (Terms, Privacy). Reuses the landing
// nav + container styling; prose styled by the `.legal*` block in globals.css.
const LegalPage: React.FC<Props> = ({ title, updated, children }) => {
  const isPrivacy = title.toLowerCase().includes('privacy');

  useEffect(() => {
    const prev = document.title;
    document.title = `${title} — GroundedIQ`;
    return () => { document.title = prev; };
  }, [title]);

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
            <div className="legal-updated">Last updated: {updated}</div>
            {children}
            <div className="legal-note">
              Questions about this policy? Email{' '}
              <a href="mailto:hello@grounded-iq.com">hello@grounded-iq.com</a>. See also our{' '}
              <Link to={isPrivacy ? '/terms' : '/privacy'}>
                {isPrivacy ? 'Terms of Service' : 'Privacy Policy'}
              </Link>.
            </div>
          </article>
        </div>
      </main>
    </div>
  );
};

export default LegalPage;
