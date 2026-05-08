import type { KpiBlock, SubscriptionBlock } from '../../types/overview';

interface Props {
  kpis: KpiBlock;
  subscription: SubscriptionBlock | null;
}

function Tile({
  label,
  value,
  sub,
  accent,
}: {
  label: string;
  value: string;
  sub?: string;
  accent?: string;
}) {
  return (
    <div
      style={{
        flex: 1,
        minWidth: 0,
        background: 'var(--surface)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-lg)',
        padding: '14px 18px',
        display: 'flex',
        flexDirection: 'column',
        gap: 4,
      }}
    >
      <p
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 9,
          letterSpacing: '.14em',
          textTransform: 'uppercase',
          color: 'var(--fg-muted)',
          margin: 0,
        }}
      >
        {label}
      </p>
      <p
        style={{
          fontFamily: 'var(--font-display)',
          fontSize: 24,
          letterSpacing: '-.02em',
          color: accent || 'var(--fg)',
          margin: 0,
          lineHeight: 1.1,
        }}
      >
        {value}
      </p>
      {sub && (
        <p
          style={{
            fontSize: 11.5,
            color: 'var(--fg-muted)',
            margin: 0,
          }}
        >
          {sub}
        </p>
      )}
    </div>
  );
}

export default function KpiStrip({ kpis, subscription }: Props) {
  const readinessPct = Math.round((kpis.avg_readiness || 0) * 100);
  const readinessColor =
    readinessPct >= 85 ? 'var(--ok)' : readinessPct >= 65 ? 'var(--warn)' : 'var(--danger)';
  const trendPct = Math.round((kpis.readiness_trend_7d || 0) * 100);
  const trendLabel =
    trendPct === 0 ? 'flat 7d' : `${trendPct > 0 ? '+' : ''}${trendPct}% last 7d`;

  const tier = subscription?.tier ? subscription.tier.toUpperCase() : 'FREE';
  const regen = subscription?.usage.report_regenerations_used ?? 0;
  const maxRegen = subscription?.limits.monthly_report_regen;
  const regenLabel =
    maxRegen == null ? `${regen} regens this month` : `${regen} / ${maxRegen} regens used`;

  return (
    <div style={{ display: 'flex', gap: 12, padding: '0 30px', marginBottom: 4 }}>
      <Tile
        label="TOTAL PROJECTS"
        value={String(kpis.total_projects)}
        sub={`${kpis.full_report_count} full · ${kpis.presales_count} pre-sales`}
      />
      <Tile
        label="AVG READINESS"
        value={`${readinessPct}%`}
        sub={trendLabel}
        accent={readinessColor}
      />
      <Tile label="PLAN" value={tier} sub={regenLabel} accent="var(--accent)" />
    </div>
  );
}
