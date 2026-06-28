// Canonical plan data — mirrors src/utils/subscription.py TIER_LIMITS in the backend.
// Every billing UI surface (PricingPage, LandingPage pricing section, UpgradeModal,
// Settings billing tab) reads from here so plans never drift from the backend.

export type Tier = 'free' | 'basic' | 'plus' | 'pro';
export type CtaKind = 'free' | 'checkout' | 'contact';

export interface PlanDescriptor {
  id: Tier;
  name: string;
  price: string;
  period: string;
  description: string;
  features: string[];
  ctaKind: CtaKind;
  ctaLabel: string;
  highlight: boolean;
  limits: {
    max_chats: number | null;            // active projects
    messages_per_chat: number | null;
    monthly_report_regen: number | null; // legacy alias (kept in sync)
    report_generations_per_month?: number | null;
    presales_per_month?: number | null;
    model_tier?: 'lite' | 'frontier';
    white_label?: boolean;
  };
}

export const PRO_CONTACT_EMAIL = 'hello@grounded-iq.com';

export const PLANS: PlanDescriptor[] = [
  {
    id: 'free',
    name: 'Free',
    price: '$0',
    period: '',
    description: 'See the full report once — on us.',
    features: [
      '1 active project',
      '1 full report / month',
      '3 presales briefs / month',
      'Watermarked PDF export',
    ],
    ctaKind: 'free',
    ctaLabel: 'Start free',
    highlight: false,
    limits: {
      max_chats: 1, messages_per_chat: 20, monthly_report_regen: 1,
      report_generations_per_month: 1, presales_per_month: 3, model_tier: 'lite', white_label: false,
    },
  },
  {
    id: 'basic',
    name: 'Basic',
    price: '$30',
    period: '/mo',
    description: 'For the solo consultant.',
    features: [
      '5 active projects',
      '10 full reports / month',
      '25 presales briefs / month',
      'Clean PDF + DOCX, deliverable builder',
      'Version history & compare · Jira push',
      'Top up anytime with credits',
    ],
    ctaKind: 'checkout',
    ctaLabel: 'Upgrade to Basic',
    highlight: false,
    limits: {
      max_chats: 5, messages_per_chat: 60, monthly_report_regen: 10,
      report_generations_per_month: 10, presales_per_month: 25, model_tier: 'lite', white_label: false,
    },
  },
  {
    id: 'plus',
    name: 'Plus',
    price: '$70',
    period: '/mo',
    description: 'Frontier reports + your brand on every export.',
    features: [
      'Frontier-model reports (sharper analysis)',
      'White-label exports (your logo & colours)',
      '15 active projects',
      '15 full reports / month, then credits',
      '100 presales briefs / month',
      'Pre-Mortem panel · section-scoped regen · priority',
    ],
    ctaKind: 'checkout',
    ctaLabel: 'Upgrade to Plus',
    highlight: true,
    limits: {
      max_chats: 15, messages_per_chat: 200, monthly_report_regen: 15,
      report_generations_per_month: 15, presales_per_month: 100, model_tier: 'frontier', white_label: true,
    },
  },
  {
    id: 'pro',
    name: 'Pro',
    price: 'Contact us',
    period: '',
    description: 'For firms — SSO, unlimited usage, governance.',
    features: [
      'Everything in Plus',
      'Unlimited projects, reports & presales (fair-use)',
      'SSO & team admin',
      'Firm project library + templates',
      'Governance & rate-card controls',
      'Dedicated support',
    ],
    ctaKind: 'contact',
    ctaLabel: 'Contact sales',
    highlight: false,
    limits: {
      max_chats: null, messages_per_chat: null, monthly_report_regen: null,
      report_generations_per_month: null, presales_per_month: null, model_tier: 'frontier', white_label: true,
    },
  },
];

export const TIER_ORDER: Tier[] = ['free', 'basic', 'plus', 'pro'];

// Credit packs — prepaid top-ups for when a plan's monthly allowance is spent.
// Mirrors config.CREDIT_PACK_GRANTS. 1 credit = $0.10 of list value; à-la-carte
// actions cost 4× our COGS (a frontier report ≈ 74 credits ≈ $7.40).
export interface CreditPack { size: '10' | '25' | '50' | '100'; price: string; credits: number; bonus?: string; }
export const CREDIT_PACKS: CreditPack[] = [
  { size: '10', price: '$10', credits: 100 },
  { size: '25', price: '$25', credits: 275, bonus: '+10%' },
  { size: '50', price: '$50', credits: 575, bonus: '+15%' },
  { size: '100', price: '$100', credits: 1250, bonus: '+25%' },
];

export function tierLabel(tier: Tier | undefined | null): string {
  if (!tier) return 'Free';
  return tier.charAt(0).toUpperCase() + tier.slice(1);
}

export function getPlan(tier: Tier): PlanDescriptor {
  return PLANS.find(p => p.id === tier) ?? PLANS[0];
}
