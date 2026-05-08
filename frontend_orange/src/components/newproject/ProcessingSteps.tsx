interface ProcessingStepsProps {
  step: number;
}

const STEPS = [
  { id: 0, label: 'Uploading document', icon: '⬆' },
  { id: 1, label: 'Extracting requirements', icon: '🔍' },
  { id: 2, label: 'Running blind spot detection', icon: '🧠' },
  { id: 3, label: 'Identifying P1 blockers', icon: '⚠' },
  { id: 4, label: 'Generating kickstart questions', icon: '❓' },
];

export default function ProcessingSteps({ step }: ProcessingStepsProps) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, padding: '20px 0' }}>
      {STEPS.map((s) => {
        const done = step > s.id;
        const active = step === s.id;
        return (
          <div
            key={s.id}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 12,
              padding: '10px 14px',
              borderRadius: 8,
              background: active
                ? 'var(--accent-soft)'
                : done
                ? 'var(--surface-2)'
                : 'transparent',
              border: `1px solid ${
                active
                  ? 'rgba(255,138,101,.3)'
                  : done
                  ? 'var(--border)'
                  : 'transparent'
              }`,
              transition: 'all .3s',
            }}
          >
            <div
              style={{
                width: 26,
                height: 26,
                borderRadius: '50%',
                background: done
                  ? 'rgba(122,229,130,.14)'
                  : active
                  ? 'var(--accent-soft)'
                  : 'var(--surface)',
                border: `1px solid ${
                  done
                    ? 'rgba(122,229,130,.3)'
                    : active
                    ? 'rgba(255,138,101,.3)'
                    : 'var(--border)'
                }`,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flexShrink: 0,
              }}
            >
              {done ? (
                <svg width="12" height="12" fill="none" stroke="var(--ok)" viewBox="0 0 24 24">
                  <polyline points="20 6 9 17 4 12" strokeWidth="2.5" strokeLinecap="round" />
                </svg>
              ) : active ? (
                <div
                  style={{
                    width: 12,
                    height: 12,
                    borderRadius: '50%',
                    border: '2px solid var(--accent)',
                    borderTopColor: 'transparent',
                    animation: 'spin 1s linear infinite',
                  }}
                />
              ) : (
                <span style={{ fontSize: 11 }}>{s.icon}</span>
              )}
            </div>
            <span
              style={{
                fontSize: 13,
                color: active ? 'var(--accent)' : done ? 'var(--fg)' : 'var(--fg-muted)',
                fontWeight: active ? 500 : 400,
              }}
            >
              {s.label}
            </span>
            {active && (
              <span
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: 9,
                  color: 'var(--accent)',
                  marginLeft: 'auto',
                  letterSpacing: '.06em',
                }}
              >
                RUNNING
              </span>
            )}
            {done && (
              <span
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: 9,
                  color: 'var(--ok)',
                  marginLeft: 'auto',
                  letterSpacing: '.06em',
                }}
              >
                DONE
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}
