import { ReactNode, CSSProperties, KeyboardEvent } from 'react';
import { useAuth } from '../../context/AuthContext';

// Cheapest tier that unlocks each gated feature — mirrors TIER_LIMITS in
// src/utils/subscription.py. Tier features are subscription-only (never credits).
const FEATURE_REQUIRED_TIER: Record<string, 'Basic' | 'Plus' | 'Pro'> = {
  version_compare: 'Basic',
  jira: 'Basic',
  deliverable_builder: 'Basic',
  docx: 'Basic',
  section_regen: 'Plus',
  pre_mortem: 'Plus',
};

function LockGlyph() {
  return (
    <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <rect x="3" y="11" width="18" height="11" rx="2" />
      <path d="M7 11V7a5 5 0 0 1 10 0v4" />
    </svg>
  );
}

interface Props {
  feature: string;
  children: ReactNode;
  /** 'overlay' (default) dims the control with a corner lock chip; 'badge' dims it
   *  and appends an inline lock chip (use where a corner chip would clip, e.g. tabs). */
  variant?: 'overlay' | 'badge';
  className?: string;
  style?: CSSProperties;
}

/**
 * Wrap a subscription-gated control. If the user's tier unlocks `feature` the children
 * render untouched; otherwise they render greyed + non-interactive, and clicking opens
 * the global UpgradeModal (via showLimitHit) instead of firing the control.
 */
export default function LockedFeature({ feature, children, variant = 'overlay', className, style }: Props) {
  const { hasFeature, showLimitHit } = useAuth();
  if (hasFeature(feature)) return <>{children}</>;

  const tier = FEATURE_REQUIRED_TIER[feature] || 'Plus';
  const open = () =>
    showLimitHit({ limit_type: `feature_${feature}`, feature, required_tier: tier.toLowerCase() });
  const onKeyDown = (e: KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); }
  };

  const chip = (
    <span
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 3,
        background: 'var(--surface-2)', border: '1px solid var(--border-strong)',
        borderRadius: 999, padding: '1px 6px 1px 5px',
        fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '.04em',
        color: 'var(--fg-dim)', lineHeight: 1.5, whiteSpace: 'nowrap',
      }}
    >
      <LockGlyph /> {tier}
    </span>
  );

  const dimmed = (
    <span style={{ opacity: 0.45, pointerEvents: 'none', filter: 'grayscale(0.35)', display: 'inline-flex' }} aria-hidden>
      {children}
    </span>
  );

  return (
    <span
      role="button"
      tabIndex={0}
      aria-label={`${tier} feature — locked, upgrade to unlock`}
      title={`${tier} feature — upgrade to unlock`}
      onClick={open}
      onKeyDown={onKeyDown}
      className={className}
      style={{
        position: 'relative',
        display: 'inline-flex',
        alignItems: 'center',
        gap: variant === 'badge' ? 6 : 0,
        cursor: 'pointer',
        ...style,
      }}
    >
      {dimmed}
      {variant === 'overlay'
        ? <span style={{ position: 'absolute', top: -7, right: -7 }}>{chip}</span>
        : chip}
    </span>
  );
}
