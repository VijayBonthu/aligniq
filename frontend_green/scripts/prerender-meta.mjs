// Build-time SEO prerender. Runs AFTER `vite build` (see package.json `build`).
//
// The site is a client-rendered SPA whose built dist/index.html is identical for
// every route, so the raw HTML crawlers and social scrapers see would be the
// homepage's on every page. This script takes the built dist/index.html as a
// template and, for each public route in src/seo/routes.mjs, rewrites the <head>
// (title, description, canonical, og:*, twitter:*) and replaces the JSON-LD block
// with that route's structured data — writing one static HTML file per route. It
// also regenerates dist/sitemap.xml from the same source. The deploy uploads each
// dist/<route>.html to the extensionless S3 key so /pricing, /about, … serve their
// own fully-described HTML at HTTP 200.

import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { SITE, ROUTES } from '../src/seo/routes.mjs';

const __dirname = dirname(fileURLToPath(import.meta.url));
const DIST = join(__dirname, '..', 'dist');
const TEMPLATE_PATH = join(DIST, 'index.html');

// HTML-attribute encode. Values may contain & and — (em dash); & / " / < / > must be
// entity-encoded so the attribute (and <title>) stay well-formed.
function escAttr(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function jsonLd(entities) {
  const graph = { '@context': 'https://schema.org', '@graph': entities };
  // Escape "<" so a value can never break out of the <script> element.
  return JSON.stringify(graph, null, 2).replace(/</g, '\\u003c');
}

// Replace a `content="…"` / `href="…"` value in a single-line tag. The regex
// captures (prefix up to the opening quote)(old value)(closing quote + tag end).
function setAttr(html, regex, value) {
  if (!regex.test(html)) {
    throw new Error(`prerender: pattern not found in index.html: ${regex}`);
  }
  return html.replace(regex, (_m, pre, _old, post) => pre + escAttr(value) + post);
}

function applyRoute(template, route) {
  const url = SITE + route.path;
  let html = template;

  html = html.replace(/(<title>)([\s\S]*?)(<\/title>)/, (_m, a, _b, c) => a + escAttr(route.title) + c);
  html = setAttr(html, /(<meta name="description" content=")([\s\S]*?)("\s*\/?>)/, route.description);
  html = setAttr(html, /(<link rel="canonical" href=")([^"]*)("\s*\/?>)/, url);
  html = setAttr(html, /(<meta property="og:title" content=")([\s\S]*?)("\s*\/?>)/, route.title);
  html = setAttr(html, /(<meta property="og:description" content=")([\s\S]*?)("\s*\/?>)/, route.description);
  html = setAttr(html, /(<meta property="og:url" content=")([^"]*)("\s*\/?>)/, url);
  html = setAttr(html, /(<meta name="twitter:title" content=")([\s\S]*?)("\s*\/?>)/, route.title);
  html = setAttr(html, /(<meta name="twitter:description" content=")([\s\S]*?)("\s*\/?>)/, route.description);

  const ldRegex = /(<script type="application\/ld\+json" id="ld-json">)([\s\S]*?)(<\/script>)/;
  if (!ldRegex.test(html)) throw new Error('prerender: <script id="ld-json"> not found in index.html');
  html = html.replace(ldRegex, (_m, open, _b, close) => `${open}\n${jsonLd(route.jsonLd)}\n    ${close}`);

  return html;
}

function buildSitemap() {
  const urls = ROUTES.map((r) => {
    const loc = r.path === '/' ? `${SITE}/` : `${SITE}${r.path}`;
    return [
      '  <url>',
      `    <loc>${loc}</loc>`,
      `    <lastmod>${r.lastmod}</lastmod>`,
      `    <changefreq>${r.changefreq}</changefreq>`,
      `    <priority>${r.priority.toFixed(1)}</priority>`,
      '  </url>',
    ].join('\n');
  }).join('\n');
  return `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls}\n</urlset>\n`;
}

function main() {
  const template = readFileSync(TEMPLATE_PATH, 'utf8');
  console.log('SEO prerender:');
  for (const route of ROUTES) {
    const html = applyRoute(template, route);
    const name = route.path === '/' ? 'index.html' : `${route.path.slice(1)}.html`;
    writeFileSync(join(DIST, name), html, 'utf8');
    console.log(`  ${name.padEnd(16)} ${route.path}`);
  }
  writeFileSync(join(DIST, 'sitemap.xml'), buildSitemap(), 'utf8');
  console.log(`  sitemap.xml      ${ROUTES.length} urls`);
}

main();
