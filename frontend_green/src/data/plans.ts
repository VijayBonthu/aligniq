// Canonical plan data — mirrors src/utils/subscription.py:21-42 in the backend.
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
    max_chats: number | null;
    messages_per_chat: number | null;
    monthly_report_regen: number | null;
  };
}

export const PRO_CONTACT_EMAIL = 'vijaybhaskarbonthu@gmail.com';

export const PLANS: PlanDescriptor[] = [
  {
    id: 'free',
    name: 'Free',
    price: '$0',
    period: '',
    description: 'Get started with the basics.',
    features: [
      '3 projects / month',
      '25 messages per chat',
      '2 report generations / month',
      'Markdown export',
    ],
    ctaKind: 'free',
    ctaLabel: 'Start free',
    highlight: false,
    limits: { max_chats: 3, messages_per_chat: 25, monthly_report_regen: 2 },
  },
  {
    id: 'basic',
    name: 'Basic',
    price: '$30',
    period: '/mo',
    description: 'For growing teams.',
    features: [
      '8 projects / month',
      '60 messages per chat',
      '6 report generations / month',
      'Email support',
    ],
    ctaKind: 'checkout',
    ctaLabel: 'Upgrade to Basic',
    highlight: false,
    limits: { max_chats: 8, messages_per_chat: 60, monthly_report_regen: 6 },
  },
  {
    id: 'plus',
    name: 'Plus',
    price: '$50',
    period: '/mo',
    description: 'More power, fewer limits.',
    features: [
      '12 projects / month',
      '80 messages per chat',
      '10 report generations / month',
      'Priority support',
    ],
    ctaKind: 'checkout',
    ctaLabel: 'Upgrade to Plus',
    highlight: true,
    limits: { max_chats: 12, messages_per_chat: 80, monthly_report_regen: 10 },
  },
  {
    id: 'pro',
    name: 'Pro',
    price: 'Contact us',
    period: '',
    description: 'Unlimited everything.',
    features: [
      'Unlimited projects',
      'Unlimited messages',
      'Unlimited report generations',
      'Named success manager',
    ],
    ctaKind: 'contact',
    ctaLabel: 'Contact sales',
    highlight: false,
    limits: { max_chats: null, messages_per_chat: null, monthly_report_regen: null },
  },
];

export const TIER_ORDER: Tier[] = ['free', 'basic', 'plus', 'pro'];

export function tierLabel(tier: Tier | undefined | null): string {
  if (!tier) return 'Free';
  return tier.charAt(0).toUpperCase() + tier.slice(1);
}

export function getPlan(tier: Tier): PlanDescriptor {
  return PLANS.find(p => p.id === tier) ?? PLANS[0];
}
