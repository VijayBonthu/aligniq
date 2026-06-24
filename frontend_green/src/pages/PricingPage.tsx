import { useState, useEffect } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { startPlanChange, getPortalUrl, buyCreditPack, PaidTier, CreditPackSize } from '../services/billingService';
import { PLANS, PRO_CONTACT_EMAIL, TIER_ORDER, CREDIT_PACKS, PlanDescriptor, Tier } from '../data/plans';
import { Logo } from '../components/Logo';

export default function PricingPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { isAuthenticated, subscription, refreshSubscription } = useAuth();
  const [loading, setLoading] = useState<string | null>(null);
  const [creditsAdded, setCreditsAdded] = useState(false);

  const currentTier: Tier | null = subscription?.tier ?? null;
  // pro is contact-sales (no self-serve Stripe portal); basic/plus self-manage.
  const isPaidUser = currentTier && currentTier !== 'free' && currentTier !== 'pro';
  const creditBalance = subscription?.credits?.balance ?? 0;

  // Returning from a credit purchase (?credits=success): the webhook grants the
  // credits asynchronously, so poll the balance a few times until it lands, then
  // drop the query param so a reload doesn't re-trigger it.
  useEffect(() => {
    if (new URLSearchParams(location.search).get('credits') !== 'success') return;
    setCreditsAdded(true);
    let n = 0;
    let timer: ReturnType<typeof setTimeout>;
    const tick = () => {
      refreshSubscription();
      if (++n < 6) timer = setTimeout(tick, 2000);  // ~10s of polling
    };
    tick();
    navigate('/pricing', { replace: true });
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.search]);

  async function handleCta(plan: PlanDescriptor) {
    if (plan.ctaKind === 'contact') {
      window.location.href = `mailto:${PRO_CONTACT_EMAIL}?subject=GroundedIQ Pro Plan`;
      return;
    }
    if (plan.ctaKind === 'free') {
      if (!isAuthenticated) navigate('/signup');
      return;
    }
    if (!isAuthenticated) {
      navigate('/login', { state: { from: '/pricing' } });
      return;
    }
    if (currentTier === plan.id) return;

    setLoading(plan.id);
    try {
      // startPlanChange handles all three outcomes: new-customer Checkout,
      // downgrade → portal, or an in-place prorated upgrade (no redirect).
      const { updated } = await startPlanChange(plan.id as PaidTier);
      if (updated) {
        window.location.reload();
        return;
      }
    } catch {
      setLoading(null);
    }
  }

  async function handleBuyCredits(size: CreditPackSize) {
    if (!isAuthenticated) {
      navigate('/login', { state: { from: '/pricing' } });
      return;
    }
    setLoading(`credits-${size}`);
    try {
      await buyCreditPack(size);
    } catch {
      setLoading(null);
    }
  }

  async function handleManage() {
    setLoading('portal');
    try {
      const { portal_url } = await getPortalUrl();
      window.location.href = portal_url;
    } catch {
      setLoading(null);
    }
  }

  function ctaLabelFor(plan: PlanDescriptor): string {
    if (currentTier === plan.id) return 'Current plan';
    if (currentTier && plan.ctaKind === 'checkout') {
      const currentIdx = TIER_ORDER.indexOf(currentTier);
      const planIdx = TIER_ORDER.indexOf(plan.id);
      if (planIdx < currentIdx) return `Downgrade to ${plan.name}`;
    }
    return plan.ctaLabel;
  }

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg)', color: 'var(--fg)' }}>
      <nav className="nav" style={{ borderBottom: '1px solid var(--border)' }}>
        <div className="container nav-inner">
          <Link to={isAuthenticated ? '/projects' : '/'}><Logo /></Link>
          <div className="nav-cta">
            {isAuthenticated ? (
              <Link to="/projects" className="btn btn-ghost">← Back to projects</Link>
            ) : (
              <>
                <Link to="/login" className="btn btn-ghost">Sign in</Link>
                <Link to="/signup" className="btn btn-primary">Start free</Link>
              </>
            )}
          </div>
        </div>
      </nav>

      <div className="container" style={{ paddingTop: 64, paddingBottom: 80 }}>
        <div style={{ textAlign: 'center', maxWidth: 720, margin: '0 auto 56px' }}>
          <p className="eyebrow" style={{ color: 'var(--accent)', marginBottom: 14 }}>
            Pricing
          </p>
          <h1 className="display" style={{ fontSize: 44, marginBottom: 16 }}>
            Simple, transparent pricing.
          </h1>
          <p style={{ fontSize: 16, color: 'var(--fg-dim)', margin: 0 }}>
            Upgrade anytime. Downgrade or cancel when you need to.
          </p>
        </div>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
            gap: 18,
            maxWidth: 1100,
            margin: '0 auto',
          }}
        >
          {PLANS.map(plan => {
            const isCurrent = currentTier === plan.id;
            const isHighlight = plan.highlight;
            return (
              <div
                key={plan.id}
                style={{
                  position: 'relative',
                  display: 'flex',
                  flexDirection: 'column',
                  padding: 24,
                  borderRadius: 'var(--radius-lg)',
                  background: isHighlight ? 'linear-gradient(180deg, rgba(52,163,123,.08), var(--surface))' : 'var(--surface)',
                  border: `1px solid ${isHighlight ? 'rgba(52,163,123,.45)' : isCurrent ? 'rgba(126,168,137,.45)' : 'var(--border)'}`,
                  boxShadow: isHighlight ? 'var(--glow)' : 'none',
                }}
              >
                {isHighlight && (
                  <span
                    className="badge badge-accent"
                    style={{
                      position: 'absolute',
                      top: -10,
                      left: '50%',
                      transform: 'translateX(-50%)',
                      padding: '4px 10px',
                      fontSize: 10,
                    }}
                  >
                    Most popular
                  </span>
                )}
                {isCurrent && (
                  <span
                    className="badge"
                    style={{
                      position: 'absolute',
                      top: -10,
                      right: 14,
                      padding: '4px 10px',
                      background: 'rgba(126,168,137,.14)',
                      color: 'var(--ok)',
                      border: '1px solid rgba(126,168,137,.3)',
                    }}
                  >
                    Current
                  </span>
                )}

                <h2
                  className="display"
                  style={{ fontSize: 22, marginBottom: 4 }}
                >
                  {plan.name}
                </h2>
                <p style={{ fontSize: 13, color: 'var(--fg-dim)', margin: 0, marginBottom: 18 }}>
                  {plan.description}
                </p>

                <div style={{ marginBottom: 22, display: 'flex', alignItems: 'baseline', gap: 4 }}>
                  <span className="display" style={{ fontSize: 32 }}>{plan.price}</span>
                  {plan.period && (
                    <span style={{ fontSize: 13, color: 'var(--fg-muted)' }}>{plan.period}</span>
                  )}
                </div>

                <ul style={{ listStyle: 'none', padding: 0, margin: 0, marginBottom: 22, flex: 1 }}>
                  {plan.features.map(f => (
                    <li
                      key={f}
                      style={{
                        display: 'flex',
                        alignItems: 'flex-start',
                        gap: 8,
                        fontSize: 13.5,
                        color: 'var(--fg)',
                        marginBottom: 10,
                      }}
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0, marginTop: 4 }}>
                        <polyline points="20 6 9 17 4 12" />
                      </svg>
                      <span>{f}</span>
                    </li>
                  ))}
                </ul>

                <button
                  className={isHighlight ? 'btn btn-primary' : isCurrent ? 'btn btn-surface' : 'btn btn-ghost'}
                  disabled={loading !== null || isCurrent || (plan.ctaKind === 'free' && isAuthenticated)}
                  onClick={() => handleCta(plan)}
                  style={{ width: '100%', justifyContent: 'center' }}
                >
                  {loading === plan.id ? 'Redirecting…' : ctaLabelFor(plan)}
                </button>
              </div>
            );
          })}
        </div>

        {/* Credit packs — prepaid top-ups, every tier. Spent when a plan's
            monthly allowance runs out (a frontier report ≈ 74 credits ≈ $7.40). */}
        <div style={{ maxWidth: 1100, margin: '56px auto 0' }}>
          <div style={{ textAlign: 'center', marginBottom: 24 }}>
            <p className="eyebrow" style={{ color: 'var(--accent)', marginBottom: 10 }}>Credits</p>
            <h2 className="display" style={{ fontSize: 28, marginBottom: 8 }}>Need more this month?</h2>
            <p style={{ fontSize: 14, color: 'var(--fg-dim)', margin: 0 }}>
              Top up anytime — credits never expire and work on any plan.{' '}
              {isAuthenticated && (
                <strong style={{ color: 'var(--fg)' }}>Balance: {creditBalance.toLocaleString()} credits</strong>
              )}
            </p>
            {creditsAdded && (
              <p style={{ fontSize: 13, color: 'var(--ok)', margin: '10px 0 0', fontWeight: 500 }}>
                ✓ Payment received — your credits are being added and will appear here within a few seconds.
              </p>
            )}
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 14 }}>
            {CREDIT_PACKS.map(pack => (
              <div
                key={pack.size}
                style={{
                  display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6,
                  padding: 20, borderRadius: 'var(--radius-lg)',
                  background: 'var(--surface)', border: '1px solid var(--border)',
                }}
              >
                <span className="display" style={{ fontSize: 26 }}>{pack.price}</span>
                <span style={{ fontSize: 13, color: 'var(--fg)' }}>
                  {pack.credits.toLocaleString()} credits
                </span>
                {pack.bonus && (
                  <span className="badge badge-accent" style={{ fontSize: 10, padding: '2px 8px' }}>{pack.bonus} bonus</span>
                )}
                <button
                  className="btn btn-ghost"
                  disabled={loading !== null}
                  onClick={() => handleBuyCredits(pack.size)}
                  style={{ width: '100%', justifyContent: 'center', marginTop: 8 }}
                >
                  {loading === `credits-${pack.size}` ? 'Redirecting…' : 'Buy credits'}
                </button>
              </div>
            ))}
          </div>
        </div>

        {isPaidUser && (
          <div
            style={{
              maxWidth: 1100,
              margin: '40px auto 0',
              padding: 22,
              borderRadius: 'var(--radius-lg)',
              border: '1px solid rgba(255,106,106,.25)',
              background: 'rgba(255,106,106,.06)',
              display: 'flex',
              flexDirection: 'row',
              flexWrap: 'wrap',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 16,
            }}
          >
            <div>
              <p style={{ fontSize: 14, fontWeight: 500, color: 'var(--fg)', margin: 0 }}>
                Manage subscription
              </p>
              <p style={{ fontSize: 12.5, color: 'var(--fg-dim)', margin: '4px 0 0' }}>
                Update billing details, view invoices, or cancel — handled by Stripe.
              </p>
            </div>
            <button
              className="btn btn-ghost"
              disabled={loading !== null}
              onClick={handleManage}
            >
              {loading === 'portal' ? 'Redirecting…' : 'Open billing portal'}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
