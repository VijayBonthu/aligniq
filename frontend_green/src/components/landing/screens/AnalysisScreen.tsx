import React, { useEffect, useState } from 'react';
import { useInView } from '../../../hooks/useInView';

const SCORE = 78;
const R = 38;
const CIRC = 2 * Math.PI * R;

const reduceMotion =
  typeof window !== 'undefined' &&
  window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

/** Step 3 — Analysis. Readiness ring that fills + counts up when in view. */
export const AnalysisScreen: React.FC = () => {
  const { ref, inView } = useInView<HTMLDivElement>({ threshold: 0.5 });
  const [shown, setShown] = useState(reduceMotion ? SCORE : 0);

  useEffect(() => {
    if (!inView) return;
    if (reduceMotion) { setShown(SCORE); return; }
    const start = performance.now();
    const dur = 900;
    let raf = 0;
    const tick = (now: number) => {
      const p = Math.min(1, (now - start) / dur);
      // easeOutCubic
      const eased = 1 - Math.pow(1 - p, 3);
      setShown(Math.round(eased * SCORE));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [inView]);

  const fill = (shown / 100) * CIRC;
  const color = SCORE >= 75 ? 'var(--ok)' : SCORE >= 50 ? 'var(--warn)' : 'var(--danger)';

  return (
    <div className="screen" ref={ref}>
      <div className="screen-bar">
        <span className="mono screen-eyebrow">procurement-workflow · Step 3 of 4</span>
        <span className="mono" style={{ marginLeft: 'auto', fontSize: 10, color: 'var(--ok)', letterSpacing: '.1em', textTransform: 'uppercase' }}>
          Ready with assumptions
        </span>
      </div>

      <div className="screen-body" style={{ padding: '20px 22px' }}>
        <p className="mono" style={{ fontSize: 10, letterSpacing: '.14em', textTransform: 'uppercase', color: 'var(--accent)', margin: '0 0 4px' }}>STEP 3 OF 4</p>
        <h3 style={{ fontFamily: 'var(--font-display)', fontSize: 20, margin: '0 0 4px', letterSpacing: '-.02em' }}>Readiness analysis</h3>
        <p style={{ fontSize: 11.5, color: 'var(--fg-muted)', margin: '0 0 16px' }}>
          GroundedIQ cross-checks every answer — hunting contradictions, flagging vagueness, scoring readiness.
        </p>

        {/* Hero ring + stats */}
        <div style={{
          display: 'grid', gridTemplateColumns: 'auto 1fr', gap: 22,
          padding: 18, background: 'var(--surface-2)',
          border: '1px solid var(--border)', borderRadius: 12,
          marginBottom: 14, alignItems: 'center',
        }}>
          <div style={{ position: 'relative', width: 96, height: 96 }}>
            <svg width="96" height="96" viewBox="0 0 100 100">
              <circle cx="50" cy="50" r={R} fill="none" stroke="var(--bg-2)" strokeWidth="5" />
              <circle cx="50" cy="50" r={R} fill="none" stroke={color} strokeWidth="5"
                strokeDasharray={`${fill} ${CIRC - fill}`} strokeDashoffset={CIRC * 0.25} strokeLinecap="round" />
            </svg>
            <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
              <span style={{ fontFamily: 'var(--font-display)', fontSize: 24, color, lineHeight: 1, letterSpacing: '-.02em' }}>{shown}</span>
              <span className="mono" style={{ fontSize: 8.5, color: 'var(--fg-muted)', letterSpacing: '.08em', textTransform: 'uppercase' }}>/ 100</span>
            </div>
          </div>
          <div>
            <p className="mono" style={{ fontSize: 9.5, color: 'var(--ok)', letterSpacing: '.1em', textTransform: 'uppercase', margin: '0 0 4px' }}>
              Ready with assumptions
            </p>
            <p style={{ fontSize: 12, color: 'var(--fg)', lineHeight: 1.5, margin: '0 0 10px' }}>
              4 of 6 critical questions answered. 2 assumptions proposed for unanswered items. No contradictions detected.
            </p>
            <div style={{ display: 'flex', gap: 14 }}>
              <div style={{ textAlign: 'center' }}>
                <p style={{ fontFamily: 'var(--font-display)', fontSize: 17, color: 'var(--danger)', lineHeight: 1, margin: 0 }}>0</p>
                <p className="mono" style={{ fontSize: 8.5, color: 'var(--fg-muted)', textTransform: 'uppercase', letterSpacing: '.06em', marginTop: 1 }}>Contradictions</p>
              </div>
              <div style={{ textAlign: 'center' }}>
                <p style={{ fontFamily: 'var(--font-display)', fontSize: 17, color: 'var(--warn)', lineHeight: 1, margin: 0 }}>1</p>
                <p className="mono" style={{ fontSize: 8.5, color: 'var(--fg-muted)', textTransform: 'uppercase', letterSpacing: '.06em', marginTop: 1 }}>Vague</p>
              </div>
              <div style={{ textAlign: 'center' }}>
                <p style={{ fontFamily: 'var(--font-display)', fontSize: 17, color: 'var(--ok)', lineHeight: 1, margin: 0 }}>2</p>
                <p className="mono" style={{ fontSize: 8.5, color: 'var(--fg-muted)', textTransform: 'uppercase', letterSpacing: '.06em', marginTop: 1 }}>Assumptions</p>
              </div>
            </div>
          </div>
        </div>

        {/* Assumptions group */}
        <div style={{ marginBottom: 10, border: '1px solid var(--border)', borderRadius: 9, overflow: 'hidden' }}>
          <div style={{ padding: '8px 12px', background: 'var(--bg-2)', borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span className="mono" style={{ fontSize: 9.5, color: 'var(--ok)', letterSpacing: '.1em', textTransform: 'uppercase' }}>Suggested assumptions · 2</span>
            <span style={{ fontSize: 11, color: 'var(--fg-muted)' }}>▾</span>
          </div>
          <div style={{ padding: '10px 12px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
              <p style={{ fontSize: 12, color: 'var(--fg)', fontWeight: 500, flex: 1, margin: 0, lineHeight: 1.4 }}>
                Assume matrix approval routing by spend tier ($10k / $50k / $250k).
              </p>
              <span className="mono" style={{ fontSize: 8.5, letterSpacing: '.08em', padding: '2px 6px', borderRadius: 4, background: 'var(--surface-2)', color: 'var(--fg-muted)', border: '1px solid var(--border)', textTransform: 'uppercase' }}>
                Low impact
              </span>
            </div>
            <p style={{ marginTop: 6, padding: '5px 8px', background: 'var(--surface-2)', borderRadius: 5, fontSize: 11, color: 'var(--fg-dim)', lineHeight: 1.45 }}>
              <span style={{ color: 'var(--accent)' }}>→ </span>If wrong: rework approval flow in W4. Add 3 days.
            </p>
          </div>
          <div style={{ padding: '10px 12px', borderTop: '1px solid var(--border)' }}>
            <p style={{ fontSize: 12, color: 'var(--fg)', fontWeight: 500, margin: 0, lineHeight: 1.4 }}>
              Assume one shared DocuSign account, migrate existing templates.
            </p>
            <p style={{ marginTop: 6, padding: '5px 8px', background: 'var(--surface-2)', borderRadius: 5, fontSize: 11, color: 'var(--fg-dim)', lineHeight: 1.45 }}>
              <span style={{ color: 'var(--accent)' }}>→ </span>If wrong: per-team accounts add 1 wk of provisioning.
            </p>
          </div>
        </div>

        {/* Action row */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10 }}>
          <button type="button" className="btn btn-ghost" style={{ padding: '8px 14px', fontSize: 12 }}>← Questions</button>
          <div style={{ display: 'flex', gap: 8 }}>
            <button type="button" className="btn btn-surface" style={{ padding: '8px 14px', fontSize: 12 }}>Apply 2 assumptions</button>
            <button type="button" className="btn btn-primary" style={{ padding: '8px 14px', fontSize: 12 }}>Generate report →</button>
          </div>
        </div>
      </div>
    </div>
  );
};
