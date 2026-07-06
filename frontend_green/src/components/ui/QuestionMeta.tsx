import type { ReactNode } from 'react';

/**
 * Shared primitives for the enterprise clarifying-question UI (wizard, chat
 * open-items drawer, public questionnaire). Inline-styled with design tokens to
 * match the existing kit (Chips/ScoreRing). One look everywhere.
 */

// ── Priority ─────────────────────────────────────────────────────────────────
export type Priority = 'blocking' | 'clarifying' | 'optional';

const PRIORITY_META: Record<Priority, { label: string; color: string }> = {
  blocking:   { label: 'Blocking',   color: 'var(--danger)' },
  clarifying: { label: 'Clarifying', color: 'var(--accent)' },
  optional:   { label: 'Optional',   color: 'var(--fg-muted)' },
};

export function PriorityPill({ priority }: { priority?: string | null }) {
  const meta = PRIORITY_META[(priority as Priority)] ?? PRIORITY_META.clarifying;
  return (
    <span
      style={{
        fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '.07em',
        textTransform: 'uppercase', padding: '2px 7px', borderRadius: 4,
        background: `color-mix(in oklab, ${meta.color} 14%, transparent)`,
        border: `1px solid color-mix(in oklab, ${meta.color} 34%, transparent)`,
        color: meta.color, flexShrink: 0, fontWeight: 600,
      }}
    >
      {meta.label}
    </span>
  );
}

// ── Respondent role ──────────────────────────────────────────────────────────
const ROLE_LABEL: Record<string, string> = {
  business: 'Business', technical: 'IT / Technical', security: 'Security', procurement: 'Procurement',
};

export function RoleChip({ role }: { role?: string | null }) {
  if (!role) return null;
  const label = ROLE_LABEL[role] || role;
  return (
    <span
      style={{
        fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '.06em',
        textTransform: 'uppercase', padding: '2px 7px', borderRadius: 4,
        background: 'var(--surface-2)', border: '1px solid var(--border)',
        color: 'var(--fg-muted)', flexShrink: 0,
      }}
      title={`Best answered by: ${label}`}
    >
      For: {label}
    </span>
  );
}

// ── Theme ────────────────────────────────────────────────────────────────────
export const THEME_LABEL: Record<string, string> = {
  systems_data: 'Systems & Data',
  identity_access: 'Identity & Access',
  payments: 'Payments',
  integration: 'Integration',
  compliance_security: 'Compliance & Security',
  scale_ops: 'Scale & Operations',
  delivery: 'Delivery',
  commercial: 'Commercial',
  other: 'Other',
};

export function themeLabel(theme?: string | null): string {
  if (!theme) return 'Other';
  return THEME_LABEL[theme] || theme.replace(/_/g, ' ');
}

export function ThemeChip({ theme }: { theme?: string | null }) {
  if (!theme) return null;
  return (
    <span
      style={{
        fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '.06em',
        textTransform: 'uppercase', padding: '2px 7px', borderRadius: 4,
        background: 'color-mix(in oklab, var(--accent) 10%, transparent)',
        border: '1px solid color-mix(in oklab, var(--accent) 22%, transparent)',
        color: 'var(--accent)', flexShrink: 0,
      }}
    >
      {themeLabel(theme)}
    </span>
  );
}

// ── Estimate impact line ─────────────────────────────────────────────────────
export function EstimateImpact({ text }: { text?: string | null }) {
  if (!text) return null;
  return (
    <div
      style={{
        display: 'flex', gap: 6, alignItems: 'baseline', marginTop: 6,
        fontSize: 12, color: 'var(--fg-dim)',
      }}
    >
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '.06em',
        textTransform: 'uppercase', color: 'var(--accent)', flexShrink: 0 }}>
        Impact
      </span>
      <span>{text}</span>
    </div>
  );
}

const RISK_COLOR: Record<string, string> = {
  high: 'var(--danger)', medium: 'var(--warn)', low: 'var(--ok)',
};

/**
 * The smart default the client can accept in one click. `onAccept` fills the
 * answer with the default text; `onOverride` focuses the answer box.
 */
export function DefaultAssumption({
  text, risk, onAccept, onOverride, accepted,
}: {
  text: string;
  risk?: string | null;
  onAccept?: () => void;
  onOverride?: () => void;
  accepted?: boolean;
}) {
  const rc = RISK_COLOR[(risk || 'medium')] || 'var(--warn)';
  return (
    <div
      style={{
        marginTop: 8, padding: '10px 12px', borderRadius: 8,
        background: 'color-mix(in oklab, var(--warn) 7%, transparent)',
        border: '1px solid color-mix(in oklab, var(--warn) 22%, transparent)',
      }}
    >
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 4 }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '.06em',
          textTransform: 'uppercase', color: 'var(--warn)' }}>
          If you don't answer, we'll assume
        </span>
        {risk ? (
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, textTransform: 'uppercase',
            color: rc }}>
            {risk} risk
          </span>
        ) : null}
      </div>
      <div style={{ fontSize: 13, color: 'var(--fg)', lineHeight: 1.5 }}>{text}</div>
      {(onAccept || onOverride) && (
        <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
          {onAccept && (
            <button
              type="button"
              onClick={onAccept}
              style={{
                fontSize: 12, padding: '5px 11px', borderRadius: 6, cursor: 'pointer',
                border: `1px solid ${accepted ? 'var(--ok)' : 'var(--border-strong)'}`,
                background: accepted ? 'color-mix(in oklab, var(--ok) 14%, transparent)' : 'var(--surface-2)',
                color: accepted ? 'var(--ok)' : 'var(--fg)', fontWeight: 500,
              }}
            >
              {accepted ? '✓ Default accepted' : 'Accept default'}
            </button>
          )}
          {onOverride && (
            <button
              type="button"
              onClick={onOverride}
              style={{
                fontSize: 12, padding: '5px 11px', borderRadius: 6, cursor: 'pointer',
                border: '1px solid var(--border)', background: 'transparent', color: 'var(--fg-dim)',
              }}
            >
              Answer instead
            </button>
          )}
        </div>
      )}
    </div>
  );
}

// ── Themed section header with progress ──────────────────────────────────────
export function ThemeSectionHeader({
  theme, answered, total, right,
}: {
  theme: string; answered: number; total: number; right?: ReactNode;
}) {
  const pct = total > 0 ? Math.round((answered / total) * 100) : 0;
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12, margin: '4px 0 10px' }}>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, letterSpacing: '.08em',
        textTransform: 'uppercase', color: 'var(--fg-dim)', fontWeight: 600 }}>
        {themeLabel(theme)}
      </div>
      <div style={{ flex: 1, height: 3, borderRadius: 2, background: 'var(--surface-2)', overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: 'var(--accent)', transition: 'width .3s' }} />
      </div>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--fg-muted)' }}>
        {answered}/{total}
      </div>
      {right}
    </div>
  );
}
