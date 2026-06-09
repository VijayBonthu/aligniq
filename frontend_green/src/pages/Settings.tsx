import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'react-hot-toast';
import { useAuth } from '../context/AuthContext';
import { getPortalUrl } from '../services/billingService';
import { connectJira, disconnectJira, getJiraStatus } from '../services/chatActionsService';
import { tierLabel } from '../data/plans';
import UsageCounter from '../components/billing/UsageCounter';
import PlanBadge from '../components/billing/PlanBadge';

type Tab = 'profile' | 'billing' | 'integrations';

export default function Settings() {
  const [tab, setTab] = useState<Tab>('billing');
  const { user, subscription, refreshSubscription } = useAuth();
  const navigate = useNavigate();
  const [busy, setBusy] = useState<string | null>(null);
  const [jiraConnected, setJiraConnected] = useState(false);
  const [jiraEmail, setJiraEmail] = useState<string | null>(null);
  const [jiraBusy, setJiraBusy] = useState(false);

  useEffect(() => {
    getJiraStatus()
      .then(s => { setJiraConnected(s.connected); setJiraEmail(s.email ?? null); })
      .catch(() => { /* leave as disconnected */ });
  }, []);

  async function connectJiraHandler() {
    setJiraBusy(true);
    try {
      await connectJira();
      const s = await getJiraStatus();
      setJiraConnected(s.connected);
      setJiraEmail(s.email ?? null);
      toast.success('Jira connected');
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not connect Jira');
    } finally {
      setJiraBusy(false);
    }
  }

  async function disconnectJiraHandler() {
    setJiraBusy(true);
    try {
      await disconnectJira();
      setJiraConnected(false);
      setJiraEmail(null);
      toast.success('Jira disconnected');
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not disconnect Jira');
    } finally {
      setJiraBusy(false);
    }
  }

  const tier = subscription?.tier ?? 'free';
  const isPaid = tier !== 'free' && tier !== 'pro';

  // Credit wallet view-model (à-la-carte costs come from the backend, so the
  // "what it buys" math stays in sync with the credit multiplier).
  const credits = subscription?.credits?.balance ?? 0;
  const creditCosts = subscription?.credits?.costs ?? {};
  const modelTier = subscription?.limits?.model_tier ?? 'lite';
  const reportCost = (modelTier === 'frontier' ? creditCosts.report_frontier : creditCosts.report_lite)
    || creditCosts.report_lite || 0;
  const reportsAffordable = reportCost > 0 ? Math.floor(credits / reportCost) : 0;
  const creditLow = reportCost > 0 && credits < reportCost;
  // Fuel gauge: full ≈ 5 reports' worth of credits (no hard max on a wallet).
  const creditPct = reportCost > 0 ? Math.min(100, Math.round((credits / (reportCost * 5)) * 100)) : 0;

  // Auto-refresh usage + balance on mount and whenever the window regains focus
  // (e.g. returning from a credit purchase), so it stays live like ChatGPT/Claude.
  useEffect(() => {
    refreshSubscription();
    const onFocus = () => refreshSubscription();
    window.addEventListener('focus', onFocus);
    return () => window.removeEventListener('focus', onFocus);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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

          {subscription?.credits && (
            <div
              style={{
                padding: 24,
                background: 'var(--surface)',
                border: `1px solid ${creditLow ? 'rgba(255,194,87,.3)' : 'var(--border)'}`,
                borderRadius: 'var(--radius-lg)',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 16, flexWrap: 'wrap' }}>
                <div>
                  <p className="eyebrow" style={{ marginBottom: 6 }}>Credit balance</p>
                  <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                    <span className="display" style={{ fontSize: 34, color: creditLow ? 'var(--warn)' : 'var(--fg)' }}>
                      {credits.toLocaleString()}
                    </span>
                    <span style={{ fontSize: 14, color: 'var(--fg-dim)' }}>credits</span>
                  </div>
                  <p style={{ fontSize: 12, color: 'var(--fg-muted)', margin: '4px 0 0', fontFamily: 'var(--font-mono)' }}>
                    ≈ {reportsAffordable} full report{reportsAffordable === 1 ? '' : 's'}
                    {creditCosts.presales ? ` · ${Math.floor(credits / creditCosts.presales)} presales briefs` : ''}
                  </p>
                </div>
                <button className="btn btn-primary" onClick={() => navigate('/pricing')}>
                  Buy credits
                </button>
              </div>
              <div style={{ marginTop: 16, height: 8, borderRadius: 4, background: 'var(--border)', overflow: 'hidden' }}>
                <div style={{ width: `${creditPct}%`, height: '100%', background: creditLow ? 'var(--warn)' : 'var(--accent)', transition: 'width .3s ease' }} />
              </div>
              {creditLow && (
                <p style={{ fontSize: 11.5, color: 'var(--warn)', margin: '8px 0 0' }}>
                  Low balance — top up to keep generating reports beyond your monthly allowance.
                </p>
              )}
            </div>
          )}

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
                  label="Reports this period"
                  current={subscription.usage.report_generations_used ?? 0}
                  limit={subscription.limits.report_generations_per_month ?? subscription.limits.monthly_report_regen}
                />
                <UsageCounter
                  label="Presales briefs"
                  current={subscription.usage.presales_used ?? 0}
                  limit={subscription.limits.presales_per_month ?? null}
                />
              </div>
              <p style={{ fontSize: 11.5, color: 'var(--fg-muted)', margin: '14px 0 0', fontFamily: 'var(--font-mono)' }}>
                Reports beyond your monthly allowance draw from credits.
                {subscription.limits.messages_per_chat != null && (
                  <> Messages are capped at {subscription.limits.messages_per_chat} per chat.</>
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
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div
            style={{
              padding: 24,
              background: 'var(--surface)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-lg)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
              <div
                style={{
                  width: 40, height: 40, borderRadius: 10, flexShrink: 0,
                  background: '#0052cc24', border: '1px solid #0052cc55', color: '#fff',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontFamily: 'var(--font-mono)', fontSize: 15, fontWeight: 700,
                }}
              >
                J
              </div>
              <div style={{ flex: 1, minWidth: 180 }}>
                <p style={{ fontSize: 14, fontWeight: 600, color: 'var(--fg)', margin: 0 }}>Jira</p>
                <p style={{ fontSize: 12.5, color: 'var(--fg-dim)', margin: '3px 0 0', lineHeight: 1.5 }}>
                  Push report risks & sections as an epic + stories, then tag, comment and move tickets
                  from inside a chat.
                </p>
                <p
                  style={{
                    fontSize: 11.5, margin: '8px 0 0', fontFamily: 'var(--font-mono)',
                    color: jiraConnected ? 'var(--ok)' : 'var(--fg-muted)',
                  }}
                >
                  {jiraConnected ? `● Connected${jiraEmail ? ` · ${jiraEmail}` : ''}` : '○ Not connected'}
                </p>
              </div>
              {jiraConnected ? (
                <button className="btn btn-ghost" onClick={disconnectJiraHandler} disabled={jiraBusy}>
                  Disconnect
                </button>
              ) : (
                <button className="btn btn-primary" onClick={connectJiraHandler} disabled={jiraBusy}>
                  {jiraBusy ? 'Waiting for Jira…' : 'Connect'}
                </button>
              )}
            </div>
          </div>

          <div
            style={{
              padding: 22,
              background: 'var(--surface)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-lg)',
              textAlign: 'center',
            }}
          >
            <p className="eyebrow" style={{ color: 'var(--accent)', marginBottom: 8 }}>Coming soon</p>
            <p style={{ fontSize: 13, color: 'var(--fg-dim)', margin: 0 }}>
              Confluence, Slack, GitHub, Notion — connect from one place.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
