import React, { useEffect, useState } from 'react';
import { useInView } from '../../../hooks/useInView';

// Stage labels mirror the presales pipeline shown on the real UploadStep.
const STEPS = [
  'Uploading document',
  'Extracting requirements',
  'Running blind spot detection',
  'Identifying P1 blockers',
  'Generating kickstart questions',
];

const reduceMotion =
  typeof window !== 'undefined' &&
  window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

/** Step 1 — Upload. A live presales-pipeline run that replays on each view. */
export const UploadScreen: React.FC = () => {
  const { ref, inView } = useInView<HTMLDivElement>({ threshold: 0.4 }, false);
  const [step, setStep] = useState(reduceMotion ? STEPS.length : 0);

  // (Re)start the run whenever the card scrolls into view.
  useEffect(() => {
    if (reduceMotion) return;
    if (inView) setStep(0);
  }, [inView]);

  // Advance one stage at a time until the run completes.
  useEffect(() => {
    if (reduceMotion || !inView) return;
    if (step >= STEPS.length) return;
    const t = setTimeout(() => setStep(s => s + 1), 1050);
    return () => clearTimeout(t);
  }, [inView, step]);

  return (
    <div className="screen" ref={ref}>
      <div className="screen-bar">
        <span className="mono screen-eyebrow">New project · Step 1 of 4</span>
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8 }}>
          <span className="screen-live-dot" />
          <span className="mono" style={{ fontSize: 10, letterSpacing: '.1em', textTransform: 'uppercase', color: 'var(--fg-dim)' }}>Live</span>
        </div>
      </div>

      <div className="screen-body" style={{ padding: '30px 26px' }}>
        <p className="mono" style={{ fontSize: 10, letterSpacing: '.14em', textTransform: 'uppercase', color: 'var(--accent)', marginBottom: 6 }}>STEP 1 OF 4</p>
        <h3 style={{ fontFamily: 'var(--font-display)', fontSize: 22, margin: '0 0 6px', letterSpacing: '-.02em', color: 'var(--fg)' }}>
          Upload your project brief
        </h3>
        <p style={{ fontSize: 12.5, color: 'var(--fg-dim)', margin: '0 0 18px', lineHeight: 1.55 }}>
          GroundedIQ scans it for ambiguities, risks, and critical unknowns in under 2 minutes.
        </p>

        {/* Uploaded file chip */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 12,
          padding: '12px 14px', borderRadius: 11, marginBottom: 16,
          background: 'var(--accent-soft)', border: '1.5px solid rgba(52,163,123,.30)',
        }}>
          <div style={{
            width: 34, height: 34, flexShrink: 0, borderRadius: 8,
            background: 'rgba(126,168,137,.18)', border: '1px solid rgba(126,168,137,.30)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <svg width="15" height="15" fill="none" stroke="var(--ok)" viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <p style={{ fontSize: 13, color: 'var(--fg)', fontWeight: 500, margin: 0 }}>procurement-rfp-q1.pdf</p>
            <p style={{ fontSize: 10.5, color: 'var(--fg-muted)', margin: '2px 0 0' }}>284 KB · PDF · DOCX · PPTX · TXT · MD · CSV</p>
          </div>
        </div>

        {/* Live presales pipeline */}
        <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12, padding: '15px 17px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 12 }}>
            <p className="mono" style={{ fontSize: 9.5, color: 'var(--accent)', letterSpacing: '.1em', textTransform: 'uppercase', margin: 0 }}>
              Presales analysis pipeline
            </p>
            <p className="mono" style={{ fontSize: 9.5, color: 'var(--fg-muted)', letterSpacing: '.06em', margin: 0 }}>
              {Math.min(step, STEPS.length)}/{STEPS.length}
            </p>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {STEPS.map((label, i) => {
              const done = step > i;
              const active = step === i;
              return (
                <div key={i} style={{
                  display: 'flex', alignItems: 'center', gap: 10,
                  padding: '8px 12px', borderRadius: 8,
                  background: active ? 'var(--accent-soft)' : done ? 'var(--surface-2)' : 'transparent',
                  border: `1px solid ${active ? 'rgba(52,163,123,.30)' : done ? 'var(--border)' : 'transparent'}`,
                  transition: 'background .25s ease, border-color .25s ease',
                }}>
                  <span style={{
                    width: 22, height: 22, borderRadius: '50%', flexShrink: 0,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    background: done ? 'rgba(126,168,137,.18)' : active ? 'var(--accent-soft)' : 'var(--surface)',
                    border: `1px solid ${done ? 'rgba(126,168,137,.3)' : active ? 'rgba(52,163,123,.30)' : 'var(--border)'}`,
                  }}>
                    {done ? (
                      <svg width="11" height="11" fill="none" stroke="var(--ok)" viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
                    ) : active ? (
                      <span style={{ width: 10, height: 10, borderRadius: '50%', border: '2px solid var(--accent)', borderTopColor: 'transparent', animation: 'spin 1s linear infinite', display: 'inline-block' }} />
                    ) : (
                      <span style={{ width: 5, height: 5, borderRadius: '50%', background: 'var(--border-strong)' }} />
                    )}
                  </span>
                  <span style={{
                    fontSize: 12, flex: 1,
                    color: done ? 'var(--fg)' : active ? 'var(--accent)' : 'var(--fg-muted)',
                    fontWeight: active ? 500 : 400,
                  }}>{label}</span>
                  {(active || done) && (
                    <span className="mono" style={{
                      fontSize: 9, letterSpacing: '.08em', textTransform: 'uppercase',
                      color: done ? 'var(--ok)' : 'var(--accent)',
                    }}>
                      {done ? 'DONE' : 'RUNNING'}
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
};
