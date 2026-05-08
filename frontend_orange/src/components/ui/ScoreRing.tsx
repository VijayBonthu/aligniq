interface ScoreRingProps {
  score: number; // 0-100
  size?: number;
}

export default function ScoreRing({ score, size = 44 }: ScoreRingProps) {
  const clamped = Math.max(0, Math.min(100, Math.round(score)));
  const r = 16;
  const circ = 2 * Math.PI * r;
  const fill = (clamped / 100) * circ;
  const color = clamped >= 85 ? 'var(--ok)' : clamped >= 65 ? 'var(--warn)' : 'var(--danger)';

  return (
    <div style={{ position: 'relative', width: size, height: size, flexShrink: 0 }}>
      <svg width={size} height={size} viewBox="0 0 44 44">
        <circle cx="22" cy="22" r={r} fill="none" stroke="var(--border-strong)" strokeWidth="2.5" />
        <circle
          cx="22"
          cy="22"
          r={r}
          fill="none"
          stroke={color}
          strokeWidth="2.5"
          strokeDasharray={`${fill} ${circ - fill}`}
          strokeDashoffset={circ * 0.25}
          strokeLinecap="round"
        />
      </svg>
      <span
        style={{
          position: 'absolute',
          inset: 0,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontFamily: 'var(--font-mono)',
          fontSize: size > 40 ? 10 : 9,
          color,
        }}
      >
        {clamped}
      </span>
    </div>
  );
}
