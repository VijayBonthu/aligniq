import { useEffect } from 'react';
import { SITE, getRoute } from '../seo/routes.mjs';

function setMeta(selector: string, attr: 'content' | 'href', value: string) {
  const el = document.head.querySelector(selector);
  if (el) el.setAttribute(attr, value);
}

/**
 * Per-route SEO head management for this SPA. The build-time prerender
 * (scripts/prerender-meta.mjs) bakes the correct title / description / canonical /
 * OG / JSON-LD into each route's static HTML from the SAME source of truth
 * (src/seo/routes.mjs), so crawlers and social scrapers get them with zero JS.
 * This hook keeps the in-page <head> correct during client-side navigation, reading
 * that same source so runtime and raw HTML can never disagree.
 *
 * Pass the route path (e.g. "/pricing"); title/description come from routes.mjs.
 * All target tags already exist in index.html, so we mutate in place.
 */
export function usePageMeta(path: string) {
  useEffect(() => {
    const route = getRoute(path);
    const url = SITE + path;

    if (route) {
      document.title = route.title;
      setMeta('meta[property="og:title"]', 'content', route.title);
      setMeta('meta[name="twitter:title"]', 'content', route.title);
      setMeta('meta[name="description"]', 'content', route.description);
      setMeta('meta[property="og:description"]', 'content', route.description);
      setMeta('meta[name="twitter:description"]', 'content', route.description);
    }
    setMeta('link[rel="canonical"]', 'href', url);
    setMeta('meta[property="og:url"]', 'content', url);
  }, [path]);
}
