import React, { useEffect, useRef, useState } from 'react';

// Hero centerpiece — a "readiness console". A large gauge fills to the score
// while the supporting counts tick up; a scan sweep + glow keep it alive.
// Decorative (aria-hidden); honours prefers-reduced-motion.

const TARGET = 78;
const RADIUS = 78;                       // in the 200×200 viewBox
const CIRC = 2 * Math.PI * RADIUS;       // ≈ 490

const STATS = [
  { label: 'Risks surfaced', value: 7 },
  { label: 'Questions raised', value: 12 },
  { label: 'Assumptions grounded', value: 4 },
];

const reduceMotion =
  typeof window !== 'undefined' &&
  window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

export const HeroVisual: React.FC = () => {
  const [p, setP] = useState(reduceMotion ? 1 : 0);
  const raf = useRef(0);

  useEffect(() => {
    if (reduceMotion) return;
    const start = performance.now();
    const dur = 1600;
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / dur);
      const eased = 1 - Math.pow(1 - t, 3); // easeOutCubic
      setP(eased);
      if (t < 1) raf.current = requestAnimationFrame(tick);
    };
    raf.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf.current);
  }, []);

  const score = Math.round(p * TARGET);
  const dashoffset = CIRC * (1 - (p * TARGET) / 100);

  return (
    <div className="hero-viz" aria-hidden="true">
      <div className="hv-glow" />

      <div className="hv-panel">
        <div className="hv-panel-top">
          <span className="mono hv-panel-label">GroundedIQ · Readiness</span>
          <span className="hv-panel-live"><span className="hv-live-dot" />ANALYZING</span>
        </div>

        <div className="hv-gauge">
          <svg viewBox="0 0 200 200" className="hv-gauge-svg">
            <circle className="hv-gauge-track" cx="100" cy="100" r={RADIUS} />
            <circle
              className="hv-gauge-fill"
              cx="100" cy="100" r={RADIUS}
              style={{ strokeDasharray: CIRC, strokeDashoffset: dashoffset }}
            />
          </svg>
          <div className="hv-gauge-mid">
            <span className="hv-gauge-num">{score}</span>
            <span className="mono hv-gauge-den">/ 100</span>
            <span className="mono hv-gauge-tag">READINESS</span>
          </div>
        </div>

        <div className="hv-stats">
          {STATS.map((s, i) => (
            <div className="hv-stat" key={s.label} style={{ animationDelay: `${0.5 + i * 0.16}s` }}>
              <span className="hv-stat-dot" />
              <span className="hv-stat-label">{s.label}</span>
              <span className="hv-stat-val">{Math.round(p * s.value)}</span>
            </div>
          ))}
        </div>

        <div className="hv-scan" />
      </div>
    </div>
  );
};
