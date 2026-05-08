import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { getPortalUrl } from '../services/billingService';
import { tierLabel } from '../data/plans';
import UsageCounter from '../components/billing/UsageCounter';
import PlanBadge from '../components/billing/PlanBadge';

type Tab = 'profile' | 'billing' | 'integrations';

export default function Settings() {
  const [tab, setTab] = useState<Tab>('billing');
  const { user, subscription, refreshSubscription } = useAuth();
  const navigate = useNavigate();
  const [busy, setBusy] = useState<string | null>(null);

  const tier = subscription?.tier ?? 'free';
  const isPaid = tier !== 'free' && tier !== 'pro';

  async function openPortal() {
    setBusy('portal');
    try {
      const { portal_url } = await getPortalUrl();
      window.location.href = portal_url;
    } catch {
      setBusy(null);
    }
  }

  async function handleRefresh() {
    setBusy('refresh');
    try {
      await refreshSubscription();
    } finally {
      setBusy(null);
    }
  }

  const periodEndStr = subscription?.period_end
    ? new Date(subscription.period_end).toLocaleDateString(undefined, {
        year: 'numeric', month: 'long', day: 'numeric',
      })
    : null;

  const statusColor = subscription?.status === 'active'
    ? 'var(--ok)'
    : subscription?.status === 'past_due'
    ? 'var(--warn)'
    : 'var(--fg-muted)';

  return (
    <div style={{ flex: 1, padding: '32px 40px', maxWidth: 920, margin: '0 auto', width: '100%' }}>
      <div style={{ marginBottom: 28 }}>
        <p className="eyebrow" style={{ color: 'var(--accent)', marginBottom: 8 }}>Settings</p>
        <h1 className="display" style={{ fontSize: 30, margin: 0 }}>Workspace</h1>
      </div>

      <div
        style={{
          display: 'flex',
          gap: 4,
          borderBottom: '1px solid var(--border)',
          marginBottom: 28,
        }}
      >
        {(['billing', 'profile', 'integrations'] as Tab[]).map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            style={{
              padding: '10px 16px',
              background: 'none',
              border: 'none',
              borderBottom: `2px solid ${tab === t ? 'var(--accent)' : 'transparent'}`,
              color: tab === t ? 'var(--fg)' : 'var(--fg-dim)',
              fontSize: 13,
              fontWeight: 500,
              cursor: 'pointer',
              fontFamily: 'var(--font-sans)',
              textTransform: 'capitalize',
              marginBottom: -1,
            }}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === 'billing' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 22 }}>
          <div
            style={{
              padding: 24,
              background: 'var(--surface)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-lg)',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 16, flexWrap: 'wrap' }}>
              <div>
                <p className="eyebrow" style={{ marginBottom: 6 }}>Current plan</p>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
                  <h2 className="display" style={{ fontSize: 28, margin: 0 }}>
                    {tierLabel(tier)}
                  </h2>
                  <PlanBadge tier={tier} size="md" />
                </div>
                {subscription && (
                  <p style={{ fontSize: 12.5, color: 'var(--fg-dim)', margin: 0, fontFamily: 'var(--font-mono)' }}>
                    Status: <span style={{ color: statusColor, textTransform: 'uppercase' }}>{subscription.status}</span>
                    {periodEndStr && isPaid && (
                      <> · Renews {periodEndStr}</>
                    )}
                  </p>
                )}
              </div>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                <button
                  className="btn btn-ghost"
                  disabled={busy !== null}
                  onClick={handleRefresh}
                >
                  {busy === 'refresh' ? 'Refreshing…' : 'Refresh'}
                </button>
                <button
                  className="btn btn-primary"
                  onClick={() => navigate('/pricing')}
                >
                  {tier === 'free' ? 'Upgrade plan' : 'Change plan'}
                </button>
              </div>
            </div>
          </div>

          {subscription && (
            <div
              style={{
                padding: 24,
                background: 'var(--surface)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-lg)',
              }}
            >
              <p className="eyebrow" style={{ marginBottom: 16 }}>Usage this period</p>
              <div style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
                gap: 14,
              }}>
                <UsageCounter
                  label="Projects this period"
                  current={subscription.usage.chats}
                  limit={subscription.limits.max_chats}
                />
                <UsageCounter
                  label="Report regenerations"
                  current={subscription.usage.report_regenerations_used}
                  limit={subscription.limits.monthly_report_regen}
                />
              </div>
              <p style={{ fontSize: 11.5, color: 'var(--fg-muted)', margin: '14px 0 0', fontFamily: 'var(--font-mono)' }}>
                Messages are tracked per chat — open a chat to see remaining sends.
                {subscription.limits.messages_per_chat != null && (
                  <> Limit: {subscription.limits.messages_per_chat} per chat.</>
                )}
              </p>
            </div>
          )}

          {isPaid && (
            <div
              style={{
                padding: 22,
                background: 'var(--surface)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-lg)',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                gap: 16,
                flexWrap: 'wrap',
              }}
            >
              <div>
                <p style={{ fontSize: 14, fontWeight: 500, margin: 0, color: 'var(--fg)' }}>
                  Manage billing
                </p>
                <p style={{ fontSize: 12.5, color: 'var(--fg-dim)', margin: '4px 0 0' }}>
                  Update card, view invoices, or cancel via Stripe.
                </p>
              </div>
              <button
                className="btn btn-ghost"
                disabled={busy !== null}
                onClick={openPortal}
              >
                {busy === 'portal' ? 'Redirecting…' : 'Open billing portal'}
              </button>
            </div>
          )}

          {!subscription && (
            <p style={{ fontSize: 13, color: 'var(--fg-dim)' }}>
              Loading plan details…
            </p>
          )}
        </div>
      )}

      {tab === 'profile' && (
        <div
          style={{
            padding: 24,
            background: 'var(--surface)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-lg)',
          }}
        >
          <p className="eyebrow" style={{ marginBottom: 12 }}>Profile</p>
          <p style={{ fontSize: 14, color: 'var(--fg)', margin: 0, marginBottom: 6 }}>
            {user?.username || user?.email}
          </p>
          <p style={{ fontSize: 12.5, color: 'var(--fg-dim)', margin: 0, fontFamily: 'var(--font-mono)' }}>
            {user?.email} · {user?.provider}
          </p>
        </div>
      )}

      {tab === 'integrations' && (
        <div
          style={{
            padding: 24,
            background: 'var(--surface)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-lg)',
            textAlign: 'center',
          }}
        >
          <p className="eyebrow" style={{ color: 'var(--accent)', marginBottom: 8 }}>Coming soon</p>
          <p style={{ fontSize: 13, color: 'var(--fg-dim)', margin: 0 }}>
            Jira, Confluence, Slack — connect from one place.
          </p>
        </div>
      )}
    </div>
  );
}
