// Single source of truth for public-page SEO — consumed by BOTH the React app
// (src/hooks/usePageMeta.ts, page components) and the build-time prerender script
// (scripts/prerender-meta.mjs). Authored as plain ESM (.mjs) so the Node prerender
// script can import it directly without a TS loader; types live in routes.d.mts.
//
// Why this exists: the site is a client-rendered SPA served as static index.html
// for every route, so the RAW HTML crawlers + social scrapers see is identical for
// every page unless we inject per-route <head> at build time. Keep titles, meta
// descriptions, canonicals, structured data, and the sitemap all derived from here
// so raw-HTML meta can never drift from what the app sets at runtime.

export const SITE = 'https://grounded-iq.com';

// ── Shared JSON-LD entities (referenced across pages by @id) ──
const organization = {
  '@type': 'Organization',
  '@id': `${SITE}/#organization`,
  name: 'GroundedIQ',
  url: `${SITE}/`,
  logo: `${SITE}/logo.svg`,
  email: 'hello@grounded-iq.com',
  description:
    'AI-powered scoping that turns a raw brief into an evidence-grounded alignment report.',
  sameAs: [
    'https://x.com/GroundedIQ',
    'https://www.instagram.com/groundediq',
    'https://www.linkedin.com/company/grounded-iq',
  ],
  contactPoint: [
    { '@type': 'ContactPoint', email: 'hello@grounded-iq.com', contactType: 'sales' },
    { '@type': 'ContactPoint', email: 'support@grounded-iq.com', contactType: 'customer support' },
  ],
};

const website = {
  '@type': 'WebSite',
  '@id': `${SITE}/#website`,
  name: 'GroundedIQ',
  url: `${SITE}/`,
  publisher: { '@id': `${SITE}/#organization` },
  inLanguage: 'en-US',
};

// Self-serve plan prices — keep in sync with src/data/plans.ts (Free/Basic/Plus).
// Pro is contact-sales and intentionally omitted from structured pricing.
const softwareApplication = {
  '@type': 'SoftwareApplication',
  '@id': `${SITE}/#software`,
  name: 'GroundedIQ',
  applicationCategory: 'BusinessApplication',
  operatingSystem: 'Web',
  url: `${SITE}/`,
  description:
    'GroundedIQ reads a project brief like a senior solution architect — surfacing risks, raising clarifying questions, and producing an evidence-grounded alignment report with architecture, timeline and resourcing before kickoff.',
  publisher: { '@id': `${SITE}/#organization` },
  offers: [
    { '@type': 'Offer', name: 'Free', price: '0', priceCurrency: 'USD' },
    { '@type': 'Offer', name: 'Basic', price: '30', priceCurrency: 'USD', category: '/month' },
    { '@type': 'Offer', name: 'Plus', price: '70', priceCurrency: 'USD', category: '/month' },
  ],
};

// ── Homepage FAQ — also rendered visibly on LandingPage (imported from here so the
// visible copy and the FAQPage structured data can never disagree). ──
export const FAQS = [
  {
    q: 'How is this different from an RFP tool?',
    a: 'RFP tools capture requirements. GroundedIQ interrogates them — it flags ambiguity, proposes architecture, and produces a doc clients actually sign off on before kickoff.',
  },
  {
    q: 'Does it replace discovery workshops?',
    a: 'No. It kills 80% of the "what did you mean by X" questions so your discovery time is spent on judgment calls, not information gathering.',
  },
  {
    q: 'What does the output look like?',
    a: 'A structured alignment report: risks ranked by severity, clarifying questions, a first-pass architecture, week-level phasing, and a resource plan. All Markdown-exportable.',
  },
  {
    q: 'Is my client data used for training?',
    a: 'No. Your documents are processed only to generate your report and are never used to train any AI models.',
  },
  {
    q: 'How do I get in touch?',
    a: 'Use the contact form for the fastest reply, or email us — hello@grounded-iq.com for general and sales questions, support@grounded-iq.com for support. You can also find us on X (@GroundedIQ), Instagram (@groundediq), and LinkedIn (Grounded IQ).',
  },
  {
    q: "I can't log in or access my account — what do I do?",
    a: 'Start with the password reset link on the sign-in page. If you\'re still stuck, the contact form works without logging in (pick "Account & login help") and a real person will get you back in.',
  },
];

// ── JSON-LD builders ──
function breadcrumb(name, path) {
  return {
    '@type': 'BreadcrumbList',
    itemListElement: [
      { '@type': 'ListItem', position: 1, name: 'Home', item: `${SITE}/` },
      { '@type': 'ListItem', position: 2, name, item: `${SITE}${path}` },
    ],
  };
}

const faqPage = {
  '@type': 'FAQPage',
  '@id': `${SITE}/#faq`,
  mainEntity: FAQS.map((f) => ({
    '@type': 'Question',
    name: f.q,
    acceptedAnswer: { '@type': 'Answer', text: f.a },
  })),
};

const pricingProduct = {
  '@type': 'Product',
  name: 'GroundedIQ',
  description:
    'AI scoping that turns a raw brief into an evidence-grounded alignment report — risks, clarifying questions, architecture, timeline and resourcing — before kickoff.',
  brand: { '@id': `${SITE}/#organization` },
  offers: {
    '@type': 'AggregateOffer',
    priceCurrency: 'USD',
    lowPrice: '0',
    highPrice: '70',
    offerCount: '3',
    offers: [
      { '@type': 'Offer', name: 'Free', price: '0', priceCurrency: 'USD', url: `${SITE}/pricing` },
      { '@type': 'Offer', name: 'Basic', price: '30', priceCurrency: 'USD', url: `${SITE}/pricing` },
      { '@type': 'Offer', name: 'Plus', price: '70', priceCurrency: 'USD', url: `${SITE}/pricing` },
    ],
  },
};

// Organization + WebSite establish the brand entity on every page; page-specific
// types (breadcrumbs, FAQ, product) are layered on per route.
const base = [organization, website];

// ── The public routes. Order = sitemap order. ──
export const ROUTES = [
  {
    path: '/',
    title: 'GroundedIQ — AI scoping & alignment reports for teams',
    description:
      'Turn a raw brief into an evidence-grounded alignment report — risks, clarifying questions, architecture, timeline and resourcing — before kickoff. GroundedIQ reads a brief like your sharpest architect.',
    lastmod: '2026-07-04',
    changefreq: 'weekly',
    priority: 1.0,
    jsonLd: [organization, website, softwareApplication, faqPage],
  },
  {
    path: '/pricing',
    title: 'Pricing — GroundedIQ',
    description:
      'GroundedIQ pricing — start free, then Basic $30/mo or Plus $70/mo with white-label exports. Turn a raw brief into an evidence-grounded scope clients sign before kickoff.',
    lastmod: '2026-07-04',
    changefreq: 'monthly',
    priority: 0.9,
    jsonLd: [...base, pricingProduct, breadcrumb('Pricing', '/pricing')],
  },
  {
    path: '/contact',
    title: 'Contact — GroundedIQ',
    description:
      'Contact GroundedIQ about sales, pricing, your account, or a bug. Reach the team via the form or email — a real person replies, usually within one business day.',
    lastmod: '2026-07-04',
    changefreq: 'monthly',
    priority: 0.8,
    jsonLd: [...base, breadcrumb('Contact', '/contact')],
  },
  {
    path: '/about',
    title: 'About GroundedIQ — why we built it',
    description:
      'Why GroundedIQ exists — closing the gap between what clients ask for and what teams build, by turning a raw brief into an evidence-grounded alignment report before kickoff.',
    lastmod: '2026-07-04',
    changefreq: 'monthly',
    priority: 0.6,
    jsonLd: [...base, breadcrumb('About', '/about')],
  },
  {
    path: '/security',
    title: 'Security & data privacy — GroundedIQ',
    description:
      'How GroundedIQ protects your data — encryption in transit and at rest, least-privilege access, and a commitment to never use your documents to train AI models.',
    lastmod: '2026-06-28',
    changefreq: 'monthly',
    priority: 0.6,
    jsonLd: [...base, breadcrumb('Security & data privacy', '/security')],
  },
  {
    path: '/changelog',
    title: "What's new — GroundedIQ",
    description:
      "What's new in GroundedIQ — a running log of shipped, user-visible product updates and improvements.",
    lastmod: '2026-07-04',
    changefreq: 'weekly',
    priority: 0.5,
    jsonLd: [...base, breadcrumb("What's new", '/changelog')],
  },
  {
    path: '/careers',
    title: 'Careers — GroundedIQ',
    description:
      'Careers at GroundedIQ — join a small, focused team building the alignment layer between what clients ask for and what gets built.',
    lastmod: '2026-07-04',
    changefreq: 'monthly',
    priority: 0.4,
    jsonLd: [...base, breadcrumb('Careers', '/careers')],
  },
  {
    path: '/privacy',
    title: 'Privacy Policy — GroundedIQ',
    description:
      'GroundedIQ Privacy Policy — what we collect, why, your rights, and our commitment to never use your documents to train AI models.',
    lastmod: '2026-06-09',
    changefreq: 'yearly',
    priority: 0.3,
    jsonLd: [...base, breadcrumb('Privacy Policy', '/privacy')],
  },
  {
    path: '/terms',
    title: 'Terms of Service — GroundedIQ',
    description:
      'GroundedIQ Terms of Service — the terms that govern your access to and use of the GroundedIQ websites, applications, and services.',
    lastmod: '2026-06-09',
    changefreq: 'yearly',
    priority: 0.3,
    jsonLd: [...base, breadcrumb('Terms of Service', '/terms')],
  },
];

export const PUBLIC_ROUTES = ROUTES.map((r) => r.path);

export function getRoute(path) {
  return ROUTES.find((r) => r.path === path);
}
