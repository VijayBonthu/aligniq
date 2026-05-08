interface Props {
  label: string;
  current: number;
  limit: number | null;
}

export default function UsageCounter({ label, current, limit }: Props) {
  const unlimited = limit === null;
  const pct = !unlimited && limit! > 0 ? current / limit! : 0;

  let color = 'var(--fg-dim)';
  let bg = 'var(--surface-2)';
  let border = 'var(--border)';
  if (!unlimited) {
    if (pct >= 1) {
      color = 'var(--danger)';
      bg = 'rgba(255,106,106,.10)';
      border = 'rgba(255,106,106,.25)';
    } else if (pct >= 0.8) {
      color = 'var(--warn)';
      bg = 'rgba(255,194,87,.10)';
      border = 'rgba(255,194,87,.25)';
    } else {
      color = 'var(--accent)';
      bg = 'var(--accent-soft)';
      border = 'rgba(255,138,101,.22)';
    }
  }

  const valueText = unlimited ? 'Unlimited' : `${current} / ${limit}`;
  const fillPct = unlimited ? 100 : Math.min(100, Math.round(pct * 100));

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 6,
        padding: '12px 14px',
        background: bg,
        border: `1px solid ${border}`,
        borderRadius: 'var(--radius)',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <span style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 10,
          textTransform: 'uppercase',
          letterSpacing: '.1em',
          color: 'var(--fg-dim)',
        }}>
          {label}
        </span>
        <span style={{ fontSize: 13, fontWeight: 500, color }}>
          {valueText}
        </span>
      </div>
      <div style={{
        height: 4,
        borderRadius: 2,
        background: 'var(--border)',
        overflow: 'hidden',
      }}>
        <div style={{
          width: `${fillPct}%`,
          height: '100%',
          background: color,
          transition: 'width .25s ease',
        }} />
      </div>
    </div>
  );
}
