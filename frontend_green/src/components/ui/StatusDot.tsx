export type StatusKind = 'active' | 'analyzing' | 'complete' | 'unknown';

interface Props {
  status: StatusKind;
  label?: string;
}

const MAP: Record<StatusKind, { color: string; label: string }> = {
  active: { color: 'var(--ok)', label: 'Active' },
  analyzing: { color: 'var(--warn)', label: 'Analyzing' },
  complete: { color: 'var(--accent)', label: 'Complete' },
  unknown: { color: 'var(--fg-muted)', label: 'Unknown' },
};

export default function StatusDot({ status, label }: Props) {
  const c = MAP[status] || MAP.unknown;
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 5,
        fontFamily: 'var(--font-mono)',
        fontSize: 10,
        letterSpacing: '.08em',
        textTransform: 'uppercase',
        color: c.color,
      }}
    >
      <span
        style={{
          width: 6,
          height: 6,
          borderRadius: '50%',
          background: c.color,
          display: 'inline-block',
          animation: status === 'analyzing' ? 'pulse 2s ease-in-out infinite' : 'none',
        }}
      />
      {label ?? c.label}
    </span>
  );
}
