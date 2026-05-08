import { Fragment } from 'react';

export type WizardPhase = 'upload' | 'questions' | 'analysis' | 'report';

const STEPS: { key: WizardPhase; label: string }[] = [
  { key: 'upload', label: 'Upload' },
  { key: 'questions', label: 'Questions' },
  { key: 'analysis', label: 'Analysis' },
  { key: 'report', label: 'Report' },
];

interface WizardStepperProps {
  phase: WizardPhase;
}

export default function WizardStepper({ phase }: WizardStepperProps) {
  const activeIdx = STEPS.findIndex((s) => s.key === phase);

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 0 }}>
      {STEPS.map((s, i) => {
        const done = i < activeIdx;
        const active = i === activeIdx;
        return (
          <Fragment key={s.key}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
              <div
                style={{
                  width: 24,
                  height: 24,
                  borderRadius: '50%',
                  background: done
                    ? 'rgba(122,229,130,.14)'
                    : active
                    ? 'var(--accent-soft)'
                    : 'var(--surface-2)',
                  border: `1px solid ${
                    done
                      ? 'rgba(122,229,130,.4)'
                      : active
                      ? 'rgba(255,138,101,.4)'
                      : 'var(--border)'
                  }`,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  transition: 'all .3s',
                }}
              >
                {done ? (
                  <svg width="10" height="10" fill="none" stroke="var(--ok)" viewBox="0 0 24 24">
                    <polyline points="20 6 9 17 4 12" strokeWidth="2.5" strokeLinecap="round" />
                  </svg>
                ) : (
                  <span
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: 9,
                      color: active ? 'var(--accent)' : 'var(--fg-muted)',
                    }}
                  >
                    {i + 1}
                  </span>
                )}
              </div>
              <span
                style={{
                  fontSize: 12,
                  color: active ? 'var(--fg)' : done ? 'var(--fg-dim)' : 'var(--fg-muted)',
                  fontWeight: active ? 500 : 400,
                }}
              >
                {s.label}
              </span>
            </div>
            {i < STEPS.length - 1 && (
              <div
                style={{
                  width: 32,
                  height: 1,
                  background: done ? 'var(--ok)' : 'var(--border)',
                  margin: '0 8px',
                  transition: 'background .4s',
                }}
              />
            )}
          </Fragment>
        );
      })}
    </div>
  );
}
