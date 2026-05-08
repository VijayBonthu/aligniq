import { Tier, tierLabel } from '../../data/plans';

interface Props {
  tier: Tier | undefined | null;
  size?: 'sm' | 'md';
}

export default function PlanBadge({ tier, size = 'sm' }: Props) {
  const t: Tier = tier ?? 'free';
  const isPaid = t !== 'free';
  return (
    <span
      className={`badge ${isPaid ? 'badge-accent' : ''}`}
      style={{
        fontSize: size === 'md' ? 11 : 10,
        padding: size === 'md' ? '4px 10px' : '3px 8px',
        background: isPaid ? 'var(--accent-soft)' : 'var(--surface-2)',
        color: isPaid ? 'var(--accent)' : 'var(--fg-dim)',
        border: `1px solid ${isPaid ? 'rgba(255,138,101,.25)' : 'var(--border)'}`,
      }}
    >
      {tierLabel(t)}
    </span>
  );
}
