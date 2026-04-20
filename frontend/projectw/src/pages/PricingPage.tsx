import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { createCheckoutSession, getPortalUrl, SubscriptionData } from '../services/billingService';

const TIERS = [
  {
    id: 'free' as const,
    name: 'Free',
    price: '$0',
    period: '',
    description: 'Get started with the basics',
    features: ['3 active chats', '25 messages per chat', '2 report generations/month'],
    cta: 'Current plan',
    highlight: false,
  },
  {
    id: 'basic' as const,
    name: 'Basic',
    price: '$30',
    period: '/mo',
    description: 'For growing teams',
    features: ['8 active chats', '60 messages per chat', '6 report generations/month'],
    cta: 'Upgrade to Basic',
    highlight: false,
  },
  {
    id: 'plus' as const,
    name: 'Plus',
    price: '$50',
    period: '/mo',
    description: 'More power, fewer limits',
    features: ['12 active chats', '80 messages per chat', '10 report generations/month'],
    cta: 'Upgrade to Plus',
    highlight: true,
  },
  {
    id: 'pro' as const,
    name: 'Pro',
    price: 'Contact us',
    period: '',
    description: 'Unlimited everything',
    features: ['Unlimited active chats', 'Unlimited messages', 'Unlimited report generations'],
    cta: 'Contact us',
    highlight: false,
  },
];

export default function PricingPage() {
  const navigate = useNavigate();
  const { isAuthenticated } = useAuth();
  const [subscription, setSubscription] = useState<SubscriptionData | null>(null);
  const [loading, setLoading] = useState<string | null>(null);

  useEffect(() => {
    if (isAuthenticated) {
      import('../services/billingService').then(({ getSubscription }) =>
        getSubscription().then(setSubscription).catch(() => {})
      );
    }
  }, [isAuthenticated]);

  async function handleCta(tier: typeof TIERS[number]) {
    if (tier.id === 'pro') {
      window.location.href = 'mailto:vijaybhaskarbonthu@gmail.com?subject=AlignIQ Pro Plan';
      return;
    }
    if (tier.id === 'free') return;

    if (!isAuthenticated) {
      navigate('/login');
      return;
    }

    // Already on this tier — do nothing (cancel button handles portal)
    if (subscription?.tier === tier.id) return;

    setLoading(tier.id);
    try {
      const { checkout_url } = await createCheckoutSession(tier.id as 'basic' | 'plus');
      window.location.href = checkout_url;
    } catch {
      setLoading(null);
    }
  }

  async function handleCancel() {
    setLoading('portal');
    try {
      const { portal_url } = await getPortalUrl();
      window.location.href = portal_url;
    } catch {
      setLoading(null);
    }
  }

  function ctaLabel(tier: typeof TIERS[number]) {
    if (subscription?.tier === tier.id) return 'Current plan';
    const tierOrder = ['free', 'basic', 'plus', 'pro'];
    const currentIdx = tierOrder.indexOf(subscription?.tier || 'free');
    const tierIdx = tierOrder.indexOf(tier.id);
    if (tierIdx < currentIdx) return `Downgrade to ${tier.name}`;
    return tier.cta;
  }

  const isPaidUser = subscription && subscription.tier !== 'free' && subscription.tier !== 'pro';

  return (
    <div className="min-h-screen bg-gray-950 py-16 px-4">
      <div className="max-w-5xl mx-auto text-center mb-12">
        <h1 className="text-4xl font-bold text-white mb-4">Simple, transparent pricing</h1>
        <p className="text-gray-400 text-lg">Upgrade anytime. Downgrade or cancel when you need to.</p>
      </div>

      <div className="max-w-5xl mx-auto grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {TIERS.map((tier) => {
          const isCurrent = subscription?.tier === tier.id;
          return (
            <div
              key={tier.id}
              className={`relative flex flex-col rounded-2xl p-6 border ${
                tier.highlight
                  ? 'bg-indigo-600/20 border-indigo-500 ring-2 ring-indigo-500'
                  : isCurrent
                  ? 'bg-gray-800 border-green-500 ring-2 ring-green-500'
                  : 'bg-gray-900 border-gray-700'
              }`}
            >
              {tier.highlight && (
                <span className="absolute -top-3 left-1/2 -translate-x-1/2 bg-indigo-500 text-white text-xs font-semibold px-3 py-1 rounded-full">
                  Most popular
                </span>
              )}
              {isCurrent && (
                <span className="absolute -top-3 left-1/2 -translate-x-1/2 bg-green-500 text-white text-xs font-semibold px-3 py-1 rounded-full">
                  Current plan
                </span>
              )}

              <h2 className="text-xl font-semibold text-white mb-1">{tier.name}</h2>
              <p className="text-gray-400 text-sm mb-4">{tier.description}</p>

              <div className="mb-6">
                <span className="text-3xl font-bold text-white">{tier.price}</span>
                <span className="text-gray-400 text-sm">{tier.period}</span>
              </div>

              <ul className="space-y-2 mb-8 flex-1">
                {tier.features.map((f) => (
                  <li key={f} className="flex items-center gap-2 text-sm text-gray-300">
                    <svg className="w-4 h-4 text-green-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                    {f}
                  </li>
                ))}
              </ul>

              <button
                onClick={() => handleCta(tier)}
                disabled={loading !== null || subscription?.tier === tier.id || tier.id === 'free'}
                className={`w-full py-2.5 px-4 rounded-lg font-medium text-sm transition-colors disabled:opacity-60 ${
                  subscription?.tier === tier.id
                    ? 'bg-green-700/40 text-green-300 cursor-default'
                    : tier.highlight
                    ? 'bg-indigo-600 hover:bg-indigo-700 text-white'
                    : tier.id === 'free'
                    ? 'bg-gray-700 text-gray-400 cursor-default'
                    : 'bg-gray-700 hover:bg-gray-600 text-white'
                }`}
              >
                {loading === tier.id ? 'Redirecting…' : ctaLabel(tier)}
              </button>
            </div>
          );
        })}
      </div>

      {isPaidUser && (
        <div className="max-w-5xl mx-auto mt-10 border border-red-900/40 bg-red-950/20 rounded-xl p-6 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div>
            <p className="text-white font-medium">Cancel subscription</p>
            <p className="text-gray-400 text-sm mt-0.5">
              You'll keep access until the end of your billing period, then drop to Free.
            </p>
          </div>
          <button
            onClick={handleCancel}
            disabled={loading !== null}
            className="shrink-0 px-5 py-2.5 rounded-lg border border-red-500 text-red-400 hover:bg-red-500/10 text-sm font-medium transition-colors disabled:opacity-50"
          >
            {loading === 'portal' ? 'Redirecting…' : 'Cancel subscription'}
          </button>
        </div>
      )}

      <div className="text-center mt-8">
        <button onClick={() => navigate('/dashboard')} className="text-gray-500 hover:text-gray-300 text-sm transition-colors">
          ← Back to dashboard
        </button>
      </div>
    </div>
  );
}
