import type { ReactNode } from 'react';

export function Tag({ children }: { children: ReactNode }) {
  return (
    <span
      style={{
        fontFamily: 'var(--font-mono)',
        fontSize: 9,
        letterSpacing: '.08em',
        textTransform: 'uppercase',
        padding: '2px 7px',
        borderRadius: 4,
        background: 'var(--surface-2)',
        border: '1px solid var(--border)',
        color: 'var(--fg-muted)',
      }}
    >
      {children}
    </span>
  );
}

export type SevLevel = 'HIGH' | 'MED' | 'LOW';

export function Sev({ level }: { level: SevLevel | string }) {
  const map: Record<string, string> = {
    HIGH: 'var(--danger)',
    MED: 'var(--warn)',
    LOW: 'var(--ok)',
  };
  const c = map[level] || 'var(--fg-muted)';
  return (
    <span
      style={{
        fontFamily: 'var(--font-mono)',
        fontSize: 9,
        padding: '2px 6px',
        borderRadius: 3,
        background: `color-mix(in oklab, ${c} 14%, transparent)`,
        color: c,
        letterSpacing: '.06em',
        textTransform: 'uppercase',
        flexShrink: 0,
      }}
    >
      {level}
    </span>
  );
}
