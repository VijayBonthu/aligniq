import { useEffect } from 'react';

// Production canonical host. Must match the canonical/og base in index.html.
const SITE = 'https://grounded-iq.com';

interface PageMeta {
  /** Full document title, e.g. "Pricing — GroundedIQ". Omit to keep the index.html default (homepage). */
  title?: string;
  /** Page-specific meta description (also fills og:description + twitter:description). */
  description?: string;
  /** Route path beginning with "/", e.g. "/pricing". Sets canonical + og:url to SITE + path. */
  path: string;
}

function setMeta(selector: string, attr: 'content' | 'href', value: string) {
  const el = document.head.querySelector(selector);
  if (el) el.setAttribute(attr, value);
}

/**
 * Per-route SEO head management for this SPA. index.html ships static homepage meta;
 * this updates title / description / canonical / og in place on navigation so each
 * marketing route self-describes — and no longer reports the homepage as its canonical
 * (the bug that made Google treat /pricing, /security, … as duplicates of /).
 *
 * Vanilla DOM (no react-helmet) to match the existing `document.title`-in-useEffect
 * idiom; Googlebot renders JS and reads these client-side updates. All target tags
 * already exist in index.html, so we mutate in place rather than inject.
 */
export function usePageMeta({ title, description, path }: PageMeta) {
  useEffect(() => {
    const url = SITE + path;

    if (title) {
      document.title = title;
      setMeta('meta[property="og:title"]', 'content', title);
      setMeta('meta[name="twitter:title"]', 'content', title);
    }
    if (description) {
      setMeta('meta[name="description"]', 'content', description);
      setMeta('meta[property="og:description"]', 'content', description);
      setMeta('meta[name="twitter:description"]', 'content', description);
    }
    setMeta('link[rel="canonical"]', 'href', url);
    setMeta('meta[property="og:url"]', 'content', url);
  }, [title, description, path]);
}
