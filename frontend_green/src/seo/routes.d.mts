// Type declarations for the plain-ESM SEO source of truth (routes.mjs). Lets the
// TypeScript app consume the same module the Node prerender script imports.

export interface Faq {
  q: string;
  a: string;
}

export interface RouteMeta {
  /** Route path beginning with "/", e.g. "/pricing". */
  path: string;
  /** Full document <title>. */
  title: string;
  /** Meta description (also fills og/twitter description). */
  description: string;
  /** ISO date (YYYY-MM-DD) for the sitemap <lastmod>. */
  lastmod: string;
  changefreq: string;
  priority: number;
  /** schema.org JSON-LD entities injected into this route's <head> at build time. */
  jsonLd: object[];
}

export const SITE: string;
export const FAQS: Faq[];
export const ROUTES: RouteMeta[];
export const PUBLIC_ROUTES: string[];
export function getRoute(path: string): RouteMeta | undefined;
