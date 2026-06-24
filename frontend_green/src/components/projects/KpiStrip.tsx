import type { KpiBlock, SubscriptionBlock } from '../../types/overview';

interface Props {
  kpis: KpiBlock;
  subscription: SubscriptionBlock | null;
  attention?: { count: number; blockers: number };
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
        display: 'flex',
        alignItems: 'center',
        gap: 11,
        minWidth: 0,
        background: 'var(--surface)',
        border: '1px solid var(--border)',
        borderRadius: 12,
        padding: '10px 14px',
      }}
    >
      <span
        style={{
          fontFamily: 'var(--font-display)',
          fontSize: 22,
          letterSpacing: '-.02em',
          color: accent || 'var(--fg)',
          lineHeight: 1,
          flexShrink: 0,
        }}
      >
        {value}
      </span>
      <div style={{ minWidth: 0 }}>
        <p
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 9,
            letterSpacing: '.12em',
            textTransform: 'uppercase',
            color: 'var(--fg-muted)',
            margin: 0,
          }}
        >
          {label}
        </p>
        {sub && (
          <p
            style={{
              fontSize: 11,
              color: 'var(--fg-muted)',
              margin: '1px 0 0',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {sub}
          </p>
        )}
      </div>
    </div>
  );
}

export default function KpiStrip({ kpis, subscription, attention }: Props) {
  const readinessPct = Math.round((kpis.avg_readiness || 0) * 100);
  const readinessColor =
    readinessPct >= 85 ? 'var(--ok)' : readinessPct >= 65 ? 'var(--warn)' : 'var(--danger)';
  const trendPct = Math.round((kpis.readiness_trend_7d || 0) * 100);
  const trendLabel =
    trendPct === 0 ? 'flat · 7d' : `${trendPct > 0 ? '+' : ''}${trendPct}% · 7d`;

  const att = attention ?? { count: 0, blockers: 0 };
  const attColor =
    att.count === 0 ? 'var(--ok)' : att.blockers >= 4 ? 'var(--danger)' : 'var(--warn)';
  const attSub =
    att.count === 0 ? 'all clear' : `${att.blockers} open blocker${att.blockers === 1 ? '' : 's'}`;

  const tier = subscription?.tier ? subscription.tier.toUpperCase() : 'FREE';
  const regen = subscription?.usage.report_regenerations_used ?? 0;
  const maxRegen = subscription?.limits.monthly_report_regen;
  const regenLabel =
    maxRegen == null ? `${regen} regens` : `${regen} / ${maxRegen} regens`;

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
        gap: 10,
        padding: '0 clamp(16px, 4vw, 30px)',
        marginBottom: 4,
      }}
    >
      <Tile
        label="TOTAL PROJECTS"
        value={String(kpis.total_projects)}
        sub={`${kpis.full_report_count} full · ${kpis.presales_count} pre-sales`}
      />
      <Tile label="AVG READINESS" value={`${readinessPct}%`} sub={trendLabel} accent={readinessColor} />
      <Tile label="NEEDS ATTENTION" value={String(att.count)} sub={attSub} accent={attColor} />
      <Tile label="PLAN" value={tier} sub={regenLabel} accent="var(--accent)" />
    </div>
  );
}
