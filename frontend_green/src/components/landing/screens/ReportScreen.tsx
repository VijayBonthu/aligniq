import React from 'react';

/** Step 4 — Report. Header bar + rendered consolidated-requirements markdown. */
export const ReportScreen: React.FC = () => {
  return (
    <div className="screen">
      <div className="screen-bar" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: 4, padding: '12px 18px' }}>
        <span className="mono screen-eyebrow" style={{ color: 'var(--accent)' }}>
          Consolidated requirements · Ready
        </span>
        <h4 style={{ fontFamily: 'var(--font-display)', fontSize: 18, margin: 0, letterSpacing: '-.02em', color: 'var(--fg)' }}>
          Procurement workflow · Q1
        </h4>
      </div>

      <div className="screen-body" style={{ padding: '20px 24px', overflowY: 'auto', maxHeight: 470 }}>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 6, marginBottom: 14 }}>
          <button type="button" className="btn btn-ghost" style={{ padding: '5px 11px', fontSize: 11 }}>Edit</button>
          <button type="button" className="btn btn-ghost" style={{ padding: '5px 11px', fontSize: 11 }}>Export ↓</button>
          <button type="button" className="btn btn-primary" style={{ padding: '5px 12px', fontSize: 11 }}>Run full pipeline →</button>
        </div>

        <div className="report-markdown" style={{ fontSize: 13 }}>
          <h1 style={{ fontFamily: 'var(--font-display)', fontSize: 20, fontWeight: 500, margin: '0 0 10px', paddingBottom: 8, borderBottom: '1px solid var(--border)', letterSpacing: '-.01em' }}>
            Executive summary
          </h1>
          <p style={{ margin: '0 0 12px', color: 'var(--fg)', lineHeight: 1.65 }}>
            Vendor-onboarding workflow integrating Coupa + DocuSign for a 200-supplier procurement org expanding to NA + EU. Readiness <b>78 / 100</b> — 4 of 6 critical questions answered, 2 assumptions applied, zero contradictions.
          </p>

          <h2 style={{ fontFamily: 'var(--font-display)', fontSize: 16, fontWeight: 500, margin: '18px 0 8px', letterSpacing: '-.01em' }}>
            P1 blockers
          </h2>
          <h3 style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--accent)', margin: '12px 0 6px', fontFamily: 'var(--font-sans)' }}>
            P1.1 · Data residency
          </h3>
          <p style={{ margin: '0 0 8px', color: 'var(--fg)', lineHeight: 1.6 }}>
            EU + NA suppliers in scope; residency strategy is <em>unspecified</em>. Confirm before architecture sign-off — determines Coupa connector topology and audit boundary.
          </p>
          <blockquote style={{
            borderLeft: '3px solid var(--accent)', padding: '8px 12px',
            margin: '8px 0 12px', background: 'var(--accent-soft)',
            borderRadius: '0 6px 6px 0', color: 'var(--fg-dim)', fontSize: 12.5, lineHeight: 1.55,
          }}>
            <b style={{ color: 'var(--fg)' }}>Status:</b> Answered · single-region EU first, NA replica in Q3. Audit boundary stays EU-only.
          </blockquote>

          <h3 style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--accent)', margin: '12px 0 6px', fontFamily: 'var(--font-sans)' }}>
            P1.2 · Coupa connector scope
          </h3>
          <p style={{ margin: '0 0 4px', color: 'var(--fg)', lineHeight: 1.6 }}>
            Read-only vs bidirectional write-back is unconfirmed. Bidirectional sync adds a 2-week middleware spike + ongoing reconciliation work.
          </p>
          <p className="mono" style={{ fontSize: 10.5, letterSpacing: '.06em', color: 'var(--warn)', margin: '6px 0', textTransform: 'uppercase' }}>
            Open · awaiting client
          </p>

          <h2 style={{ fontFamily: 'var(--font-display)', fontSize: 16, fontWeight: 500, margin: '18px 0 8px', letterSpacing: '-.01em' }}>
            Assumptions log
          </h2>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12, margin: '0 0 12px' }}>
            <thead>
              <tr>
                <th style={{ padding: '6px 9px', border: '1px solid var(--border)', background: 'var(--surface-2)', textAlign: 'left', fontWeight: 600, fontSize: 11, textTransform: 'uppercase', letterSpacing: '.04em' }}>For</th>
                <th style={{ padding: '6px 9px', border: '1px solid var(--border)', background: 'var(--surface-2)', textAlign: 'left', fontWeight: 600, fontSize: 11, textTransform: 'uppercase', letterSpacing: '.04em' }}>Assumption</th>
                <th style={{ padding: '6px 9px', border: '1px solid var(--border)', background: 'var(--surface-2)', textAlign: 'left', fontWeight: 600, fontSize: 11, textTransform: 'uppercase', letterSpacing: '.04em' }}>Impact if wrong</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td style={{ padding: '6px 9px', border: '1px solid var(--border)', color: 'var(--fg-dim)' }}>K.1</td>
                <td style={{ padding: '6px 9px', border: '1px solid var(--border)', color: 'var(--fg)' }}>Matrix routing by tier ($10k/$50k/$250k)</td>
                <td style={{ padding: '6px 9px', border: '1px solid var(--border)', color: 'var(--fg-dim)' }}>Low · 3 days rework</td>
              </tr>
              <tr style={{ background: 'var(--surface-2)' }}>
                <td style={{ padding: '6px 9px', border: '1px solid var(--border)', color: 'var(--fg-dim)' }}>K.2</td>
                <td style={{ padding: '6px 9px', border: '1px solid var(--border)', color: 'var(--fg)' }}>One shared DocuSign acct</td>
                <td style={{ padding: '6px 9px', border: '1px solid var(--border)', color: 'var(--fg-dim)' }}>Med · 1 wk provisioning</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
