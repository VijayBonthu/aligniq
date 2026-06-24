import React, { useEffect, useState } from 'react';
import { useInView } from '../../../hooks/useInView';

// Stage labels are EXACT from CONTRACT_STAGES in
// frontend_orange/src/components/pipeline/PipelineProgress.tsx, which mirrors
// CONTRACT_PIPELINE_STAGES_ORDER in src/database_scripts.py.
const STAGES = [
  { id: 'plan',               label: 'Planning report contract',     note: '' },
  { id: 'decide',             label: 'Deciding solution & estimate', note: '' },
  { id: 'write_sections',     label: 'Writing sections in parallel', note: 'parallel' },
  { id: 'judge_and_finalize', label: 'Judging and finalizing',       note: 'scoring' },
];

const reduceMotion =
  typeof window !== 'undefined' &&
  window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

/** Optional — the full report pipeline. Live-streamed 4-stage progress. */
export const PipelineScreen: React.FC = () => {
  const { ref, inView } = useInView<HTMLDivElement>({ threshold: 0.4 }, false);
  const [currentIdx, setCurrentIdx] = useState(reduceMotion ? STAGES.length : 2);

  useEffect(() => {
    if (reduceMotion || !inView) return;
    const id = setInterval(() => {
      setCurrentIdx(i => (i + 1) % (STAGES.length + 1));
    }, 2200);
    return () => clearInterval(id);
  }, [inView]);

  return (
    <div className="screen" ref={ref}>
      <div className="screen-bar">
        <span className="mono screen-eyebrow">Generating full report</span>
        <span className="mono" style={{ marginLeft: 'auto', fontSize: 10, color: 'var(--accent)', letterSpacing: '.1em', textTransform: 'uppercase' }}>
          4-stage pipeline · running
        </span>
      </div>

      <div className="screen-body" style={{ padding: '22px 24px' }}>
        <h3 style={{ fontFamily: 'var(--font-display)', fontSize: 19, margin: '0 0 4px', letterSpacing: '-.02em', color: 'var(--fg)' }}>
          Running the full report pipeline
        </h3>
        <p style={{ fontSize: 11.5, color: 'var(--fg-muted)', margin: '0 0 18px', lineHeight: 1.55 }}>
          Plan the contract, lock the typed decisions, write every section in parallel, then judge. Runs in the background — leave the page and come back; the run resumes.
        </p>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {STAGES.map((s, i) => {
            const isDone = i < currentIdx;
            const isActive = i === currentIdx;
            return (
              <div key={s.id} style={{
                display: 'flex', alignItems: 'center', gap: 11,
                padding: '11px 13px', borderRadius: 9,
                background: isActive ? 'var(--accent-soft)' : isDone ? 'var(--surface-2)' : 'transparent',
                border: `1px solid ${isActive ? 'rgba(52,163,123,.30)' : isDone ? 'var(--border)' : 'transparent'}`,
                transition: 'background .2s ease, border-color .2s ease',
              }}>
                <span className="mono" style={{ fontSize: 10, color: isActive ? 'var(--accent)' : 'var(--fg-muted)', minWidth: 18, letterSpacing: '.04em' }}>
                  {String(i + 1).padStart(2, '0')}
                </span>
                <span style={{
                  width: 22, height: 22, borderRadius: '50%', flexShrink: 0,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  background: isDone ? 'rgba(126,168,137,.18)' : isActive ? 'var(--accent-soft)' : 'var(--surface)',
                  border: `1px solid ${isDone ? 'rgba(126,168,137,.3)' : isActive ? 'rgba(52,163,123,.3)' : 'var(--border)'}`,
                }}>
                  {isDone ? (
                    <svg width="11" height="11" fill="none" stroke="var(--ok)" viewBox="0 0 24 24"><path d="M5 13l4 4L19 7" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" /></svg>
                  ) : isActive ? (
                    <span style={{ width: 10, height: 10, borderRadius: '50%', border: '2px solid rgba(52,163,123,.3)', borderTopColor: 'var(--accent)', animation: 'spin 1s linear infinite' }} />
                  ) : (
                    <span style={{ width: 4, height: 4, borderRadius: '50%', background: 'var(--border-strong)' }} />
                  )}
                </span>
                <span style={{
                  flex: 1, fontSize: 12.5,
                  fontWeight: isActive ? 500 : 400,
                  color: isActive ? 'var(--accent)' : isDone ? 'var(--fg)' : 'var(--fg-muted)',
                }}>{s.label}</span>
                {s.note && isActive && (
                  <span className="mono" style={{ fontSize: 9, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--warn)' }}>{s.note}</span>
                )}
                {isActive && (
                  <span className="mono" style={{ fontSize: 9, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--accent)', animation: 'pulse 2s ease-in-out infinite' }}>
                    Running
                  </span>
                )}
                {isDone && (
                  <span className="mono" style={{ fontSize: 9, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--ok)' }}>Done</span>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};
