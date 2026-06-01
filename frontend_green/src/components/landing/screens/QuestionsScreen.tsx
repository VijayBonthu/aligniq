import React, { useState } from 'react';

type AnswerKey = 'p1_0' | 'p1_1' | 'q_0' | 'q_1';

interface P1Item { id: number; blocker: string; why: string; cat: string; }
interface KickItem { id: number; q: string; cat: string; }

const P1: P1Item[] = [
  { id: 1, blocker: 'Data residency strategy for EU + NA suppliers is unspecified.', why: 'Determines Coupa connector topology and audit boundary. Affects W1-3 estimate.', cat: 'Architecture' },
  { id: 2, blocker: 'Coupa connector scope — read-only or bidirectional write-back?', why: 'Bidirectional sync adds a 2-week middleware spike + ongoing reconciliation work.', cat: 'Integrations' },
];
const KICK: KickItem[] = [
  { id: 1, q: 'Approval policy — single-step or matrix routing by spend tier?', cat: 'Workflow' },
  { id: 2, q: 'Supplier portal scope — self-serve onboarding or admin-managed?', cat: 'UX' },
];

/** Step 2 — Questions. P1 blockers (with "why it matters") + kickstart cards. */
export const QuestionsScreen: React.FC = () => {
  const [answers, setAnswers] = useState<Record<AnswerKey, string>>({
    p1_0: '',
    p1_1: 'Single-region EU first, then NA replica in Q3. Audit boundary stays EU-only.',
    q_0: '',
    q_1: '',
  });
  const total = 4;
  const answered = Object.values(answers).filter(v => v.trim()).length;

  return (
    <div className="screen">
      <div className="screen-bar">
        <span className="mono screen-eyebrow">procurement-workflow · Step 2 of 4</span>
        <div style={{ marginLeft: 'auto', textAlign: 'right' }}>
          <div style={{ fontFamily: 'var(--font-display)', fontSize: 18, color: 'var(--fg)', lineHeight: 1 }}>{answered}</div>
          <div className="mono" style={{ fontSize: 9, color: 'var(--fg-muted)', letterSpacing: '.06em', textTransform: 'uppercase' }}>
            / {total} answered
          </div>
        </div>
      </div>

      <div className="screen-body" style={{ padding: '20px 22px' }}>
        <p className="mono" style={{ fontSize: 10, letterSpacing: '.14em', textTransform: 'uppercase', color: 'var(--accent)', margin: '0 0 4px' }}>STEP 2 OF 4</p>
        <h3 style={{ fontFamily: 'var(--font-display)', fontSize: 20, margin: '0 0 4px', letterSpacing: '-.02em' }}>Answer the questions</h3>
        <p style={{ fontSize: 11.5, color: 'var(--fg-muted)', margin: '0 0 14px' }}>
          Answer what you can. Anything left blank can be auto-filled with assumptions in the next step.
        </p>

        {/* Progress bar */}
        <div style={{ height: 3, background: 'var(--border)', borderRadius: 2, overflow: 'hidden', marginBottom: 18 }}>
          <div style={{ height: '100%', width: `${(answered / total) * 100}%`, background: 'linear-gradient(90deg, var(--accent), var(--accent-2))', borderRadius: 2, transition: 'width .4s ease' }} />
        </div>

        {/* P1 GROUP */}
        <p className="mono" style={{ fontSize: 9.5, color: 'var(--danger)', letterSpacing: '.1em', textTransform: 'uppercase', margin: '0 0 8px' }}>
          P1 BLOCKERS · {P1.length} CRITICAL <span style={{ color: 'var(--fg-muted)', textTransform: 'none', letterSpacing: 0 }}>— Must answer before report</span>
        </p>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 14 }}>
          {P1.map((b, idx) => {
            const key = `p1_${idx}` as AnswerKey;
            const filled = !!answers[key]?.trim();
            return (
              <div key={b.id} style={{ border: '1px solid rgba(200,113,113,.22)', borderRadius: 9, background: 'rgba(200,113,113,.05)', overflow: 'hidden' }}>
                <div style={{ padding: '10px 12px 6px', display: 'flex', gap: 8, alignItems: 'flex-start' }}>
                  <span className="mono" style={{
                    fontSize: 9, letterSpacing: '.08em', padding: '2px 6px', borderRadius: 4,
                    background: 'var(--surface-2)', color: 'var(--danger)', border: '1px solid rgba(200,113,113,.22)',
                    flexShrink: 0,
                  }}>P1-{idx + 1}</span>
                  <div style={{ flex: 1 }}>
                    <p style={{ fontSize: 12, fontWeight: 600, color: 'var(--fg)', margin: 0, lineHeight: 1.4 }}>{b.blocker}</p>
                    <p style={{ fontSize: 11, color: 'var(--fg-dim)', margin: '3px 0 0', lineHeight: 1.45 }}>{b.why}</p>
                    <span className="mono" style={{
                      display: 'inline-block', marginTop: 5, fontSize: 8.5, letterSpacing: '.08em',
                      padding: '2px 6px', borderRadius: 4, background: 'var(--surface-2)',
                      color: 'var(--fg-muted)', border: '1px solid var(--border)', textTransform: 'uppercase',
                    }}>{b.cat}</span>
                  </div>
                </div>
                <div style={{ padding: '0 12px 10px' }}>
                  <textarea
                    value={answers[key]}
                    onChange={e => setAnswers(a => ({ ...a, [key]: e.target.value }))}
                    placeholder="Provide your answer here…"
                    rows={1}
                    style={{
                      width: '100%', background: 'var(--surface-2)',
                      border: `1px solid ${filled ? 'rgba(126,168,137,.3)' : 'var(--border)'}`,
                      borderRadius: 6, padding: '7px 10px',
                      color: 'var(--fg)', fontSize: 11.5,
                      fontFamily: 'var(--font-sans)', resize: 'none', outline: 'none',
                      transition: 'border-color .2s', minHeight: 28,
                    }}
                  />
                </div>
              </div>
            );
          })}
        </div>

        {/* KICKSTART */}
        <p className="mono" style={{ fontSize: 9.5, color: 'var(--accent)', letterSpacing: '.1em', textTransform: 'uppercase', margin: '0 0 8px' }}>
          KICKSTART QUESTIONS · {KICK.length} ITEMS
        </p>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {KICK.map((k, idx) => (
            <div key={k.id} style={{ border: '1px solid var(--border)', borderRadius: 9, overflow: 'hidden' }}>
              <div style={{ padding: '10px 12px 6px', display: 'flex', gap: 8, alignItems: 'flex-start' }}>
                <span className="mono" style={{
                  fontSize: 9, letterSpacing: '.08em', padding: '2px 6px', borderRadius: 4,
                  background: 'var(--surface-2)', color: 'var(--accent)', border: '1px solid var(--border)',
                }}>Q-{idx + 1}</span>
                <div style={{ flex: 1 }}>
                  <p style={{ fontSize: 12, fontWeight: 500, color: 'var(--fg)', margin: 0, lineHeight: 1.4 }}>{k.q}</p>
                  <span className="mono" style={{
                    display: 'inline-block', marginTop: 5, fontSize: 8.5, letterSpacing: '.08em',
                    padding: '2px 6px', borderRadius: 4, background: 'var(--surface-2)',
                    color: 'var(--fg-muted)', border: '1px solid var(--border)', textTransform: 'uppercase',
                  }}>{k.cat}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
