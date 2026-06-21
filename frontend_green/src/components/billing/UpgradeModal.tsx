import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { startPlanChange } from '../../services/billingService';

// Usage caps (extendable with prepaid credits) vs. feature gates (subscription-only).
type UsageLimitType =
  | 'max_chats'
  | 'messages_per_chat'
  | 'monthly_report_regen'
  | 'report_generations_per_month'
  | 'presales_per_month';

export type LimitType = UsageLimitType | `feature_${string}`;

export interface LimitHitDetail {
  limit_type: LimitType;
  current?: number;
  limit?: number;
  upgrade_url?: string;
  // Set by the report/presales/message metering when credit top-up is available.
  credit_overage?: boolean;
  credit_cost?: number;
  credit_balance?: number;
  // Set for feature gates (limit_type 'feature_*'): the flag and the tier that unlocks it.
  feature?: string;
  required_tier?: string;
}

interface Props {
  open: boolean;
  detail: LimitHitDetail | null;
  onClose: () => void;
}

const LIMIT_HEADLINES: Record<UsageLimitType, string> = {
  max_chats: 'You have reached your active project limit.',
  messages_per_chat: 'You have reached the message limit for this chat.',
  monthly_report_regen: 'You have used all your monthly reports.',
  report_generations_per_month: 'You have used all your monthly reports.',
  presales_per_month: 'You have used all your monthly presales briefs.',
};

const LIMIT_SUB: Record<UsageLimitType, string> = {
  max_chats: 'Upgrade to start more parallel projects.',
  messages_per_chat: 'Recharge credits or upgrade to keep the conversation going.',
  monthly_report_regen: 'Recharge credits or upgrade for more reports.',
  report_generations_per_month: 'Recharge credits or upgrade for more reports.',
  presales_per_month: 'Recharge credits or upgrade to run more briefs.',
};

// Friendly names for feature gates (limit_type 'feature_<key>').
const FEATURE_LABELS: Record<string, string> = {
  version_compare: 'Version compare',
  jira: 'Jira push',
  deliverable_builder: 'Deliverable Builder',
  docx: 'DOCX export',
  section_regen: 'Section polish',
  pre_mortem: 'Pre-Mortem',
};

export default function UpgradeModal({ open, detail, onClose }: Props) {
  const navigate = useNavigate();
  const [loading, setLoading] = useState<string | null>(null);

  if (!open || !detail) return null;

  const handleUpgrade = async (tier: 'basic' | 'plus') => {
    setLoading(tier);
    try {
      const { updated } = await startPlanChange(tier);
      if (updated) {
        // In-place upgrade applied (existing subscriber) — no redirect happened.
        // Reload so the unlocked tier/limits take effect across the app.
        window.location.reload();
        return;
      }
      // Otherwise startPlanChange already navigated to Checkout / the Portal.
    } catch {
      setLoading(null);
    }
  };

  const handleViewAll = () => {
    onClose();
    navigate('/pricing');
  };

  const isFeature = detail.limit_type.startsWith('feature_');
  const requiredTier = (detail.required_tier || 'plus').toLowerCase();
  const tierCap = requiredTier.charAt(0).toUpperCase() + requiredTier.slice(1);
  const featureName = FEATURE_LABELS[detail.feature || ''] || 'This';
  const headline = isFeature
    ? `${featureName} is a ${tierCap} feature.`
    : LIMIT_HEADLINES[detail.limit_type as UsageLimitType];
  const sub = isFeature
    ? `Upgrade to ${tierCap} to unlock it — it isn't available on your current plan.`
    : LIMIT_SUB[detail.limit_type as UsageLimitType];
  // Usage caps can be topped up with credits; feature gates cannot.
  const showCredits = !isFeature && !!detail.credit_overage;
  const showUsage = !isFeature && typeof detail.current === 'number' && typeof detail.limit === 'number';
  // Only offer tiers that actually unlock the gated feature.
  const showBasic = !isFeature || requiredTier === 'basic';
  const showPlus = !isFeature || requiredTier === 'basic' || requiredTier === 'plus';

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 1000,
        background: 'rgba(0,0,0,.6)',
        backdropFilter: 'blur(4px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 20,
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          width: '100%',
          maxWidth: 460,
          background: 'var(--surface)',
          border: '1px solid var(--border-strong)',
          borderRadius: 'var(--radius-lg)',
          padding: 28,
          boxShadow: 'var(--shadow-lg)',
        }}
      >
        <p style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 10,
          letterSpacing: '.14em',
          textTransform: 'uppercase',
          color: 'var(--accent)',
          margin: 0,
          marginBottom: 10,
        }}>
          {isFeature ? 'Upgrade required' : 'Limit reached'}
        </p>
        <h2 style={{
          fontFamily: 'var(--font-display)',
          fontWeight: 400,
          letterSpacing: '-.02em',
          fontSize: 22,
          color: 'var(--fg)',
          margin: 0,
          marginBottom: 8,
        }}>
          {headline}
        </h2>
        <p style={{ fontSize: 13.5, color: 'var(--fg-dim)', margin: 0, marginBottom: showUsage ? 6 : 20 }}>
          {sub}
        </p>
        {showUsage && (
          <p style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            color: 'var(--fg-muted)',
            margin: 0,
            marginBottom: showCredits ? 8 : 20,
          }}>
            Usage: {detail.current} / {detail.limit}
          </p>
        )}
        {showCredits && (
          <p style={{ fontSize: 12.5, color: 'var(--fg-dim)', margin: 0, marginBottom: 20 }}>
            {typeof detail.credit_cost === 'number'
              ? `Or keep going with credits — ${detail.credit_cost} credits each`
              : 'Or keep going with prepaid credits'}
            {typeof detail.credit_balance === 'number' && ` (balance: ${detail.credit_balance}).`}
          </p>
        )}

        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {showCredits && (
            <button
              className="btn btn-primary"
              disabled={loading !== null}
              onClick={handleViewAll}
              style={{ width: '100%', justifyContent: 'center' }}
            >
              Recharge credits
            </button>
          )}
          {showBasic && (
            <button
              className={showCredits ? 'btn btn-surface' : 'btn btn-primary'}
              disabled={loading !== null}
              onClick={() => handleUpgrade('basic')}
              style={{ width: '100%', justifyContent: 'center' }}
            >
              {loading === 'basic' ? 'Redirecting…' : 'Upgrade to Basic — $30/mo'}
            </button>
          )}
          {showPlus && (
            <button
              className="btn btn-surface"
              disabled={loading !== null}
              onClick={() => handleUpgrade('plus')}
              style={{ width: '100%', justifyContent: 'center' }}
            >
              {loading === 'plus' ? 'Redirecting…' : 'Upgrade to Plus — $70/mo'}
            </button>
          )}
          <button
            className="btn btn-ghost"
            disabled={loading !== null}
            onClick={handleViewAll}
            style={{ width: '100%', justifyContent: 'center' }}
          >
            View all plans
          </button>
        </div>

        <button
          onClick={onClose}
          style={{
            width: '100%',
            background: 'none',
            border: 'none',
            color: 'var(--fg-muted)',
            fontSize: 12,
            marginTop: 16,
            cursor: 'pointer',
            fontFamily: 'var(--font-mono)',
            letterSpacing: '.06em',
            textTransform: 'uppercase',
          }}
        >
          Maybe later
        </button>
      </div>
    </div>
  );
}
