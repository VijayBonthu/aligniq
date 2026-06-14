import { useCallback, useEffect, useRef, useState } from 'react';
import { toast } from 'react-hot-toast';
import { notifyError } from '../../services/api';
import {
  getContractCost,
  previewContractCost,
  saveContractCost,
  type CostLineEdit,
  type CostTotals,
} from '../../services/chatActionsService';

interface Props {
  chatHistoryId: string;
  open: boolean;
  onClose: () => void;
  /** Called after a save creates a new version, so the host can reload the report. */
  onSaved?: () => void | Promise<void>;
}

const money = (n?: number | null) => (n == null ? '—' : `$${Math.round(n).toLocaleString()}`);
const blankLine = (): CostLineEdit => ({ workstream: '', role: '', seniority: '', hours_low: 0, hours_high: 0, rate_usd: 0 });

export default function CostEditor({ chatHistoryId, open, onClose, onSaved }: Props) {
  const [lines, setLines] = useState<CostLineEdit[]>([]);
  const [contingency, setContingency] = useState(0);
  const [totals, setTotals] = useState<CostTotals | null>(null);
  const [rateNotes, setRateNotes] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [legacy, setLegacy] = useState(false);
  const previewTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = useCallback(async () => {
    if (!chatHistoryId) return;
    setLoading(true);
    setLegacy(false);
    try {
      const data = await getContractCost(chatHistoryId);
      setLines(data.cost_lines.length ? data.cost_lines : [blankLine()]);
      setContingency(data.contingency_pct ?? 0);
      setTotals(data.totals);
      setRateNotes([]);
    } catch (err) {
      // 409 = legacy report with no structured cost model.
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status === 409) setLegacy(true);
      else notifyError(err, 'Could not load the cost estimate');
    } finally {
      setLoading(false);
    }
  }, [chatHistoryId]);

  useEffect(() => { if (open) void load(); }, [open, load]);

  // Debounced server preview — the firm rate card is applied server-side, so the
  // shown totals match what a save will produce.
  const schedulePreview = useCallback((nextLines: CostLineEdit[], nextContingency: number) => {
    if (previewTimer.current) clearTimeout(previewTimer.current);
    previewTimer.current = setTimeout(async () => {
      const valid = nextLines.filter((l) => l.role.trim() && l.hours_low >= 0 && l.hours_high >= 0);
      if (!valid.length) return;
      try {
        const r = await previewContractCost(chatHistoryId, nextLines, nextContingency);
        setTotals(r.totals);
        setRateNotes(r.rate_notes || []);
      } catch {
        // preview is best-effort; ignore transient errors
      }
    }, 400);
  }, [chatHistoryId]);

  const update = (next: CostLineEdit[], nextContingency = contingency) => {
    setLines(next);
    setContingency(nextContingency);
    schedulePreview(next, nextContingency);
  };

  const setField = (i: number, field: keyof CostLineEdit, value: string) => {
    const next = lines.map((l, idx) => {
      if (idx !== i) return l;
      const numeric = field === 'hours_low' || field === 'hours_high' || field === 'rate_usd';
      return { ...l, [field]: numeric ? Number(value) || 0 : value };
    });
    update(next);
  };

  const addRow = () => update([...lines, blankLine()]);
  const removeRow = (i: number) => update(lines.filter((_, idx) => idx !== i));

  const save = async () => {
    const valid = lines.filter((l) => l.role.trim());
    if (!valid.length) { toast.error('Add at least one role'); return; }
    setSaving(true);
    try {
      const r = await saveContractCost(chatHistoryId, valid, contingency);
      toast.success(`Saved as v${r.version_number}${r.cost_table_replaced ? '' : ' (cost table not found in report body)'}`);
      await onSaved?.();
      onClose();
    } catch (err) {
      notifyError(err, 'Could not save the cost estimate');
    } finally {
      setSaving(false);
    }
  };

  if (!open) return null;

  return (
    <div style={overlay} onClick={onClose}>
      <div style={drawer} onClick={(e) => e.stopPropagation()}>
        <div style={header}>
          <span style={titleStyle}>Edit estimate</span>
          <button onClick={onClose} style={closeBtn} title="Close">✕</button>
        </div>
        <p style={hint}>
          Edit roles, hours, and rates. Rates auto-apply your firm rate card where a role matches.
          Saving creates a new version instantly — no pipeline regen.
        </p>

        <div style={{ flex: 1, overflowY: 'auto', padding: '0 14px 14px' }}>
          {loading ? (
            <p style={muted}>Loading…</p>
          ) : legacy ? (
            <p style={muted}>This report has no structured cost model to edit. Regenerate it through the pipeline to get one.</p>
          ) : (
            <>
              <table style={table}>
                <thead>
                  <tr>
                    <th style={th}>Workstream</th>
                    <th style={th}>Role</th>
                    <th style={th}>Seniority</th>
                    <th style={thNum}>Hrs low</th>
                    <th style={thNum}>Hrs high</th>
                    <th style={thNum}>Rate</th>
                    <th style={th}></th>
                  </tr>
                </thead>
                <tbody>
                  {lines.map((l, i) => (
                    <tr key={i}>
                      <td style={td}><input style={inp} value={l.workstream} onChange={(e) => setField(i, 'workstream', e.target.value)} /></td>
                      <td style={td}><input style={inp} value={l.role} onChange={(e) => setField(i, 'role', e.target.value)} /></td>
                      <td style={td}><input style={{ ...inp, width: 64 }} value={l.seniority || ''} onChange={(e) => setField(i, 'seniority', e.target.value)} /></td>
                      <td style={td}><input style={inpNum} type="number" value={l.hours_low} onChange={(e) => setField(i, 'hours_low', e.target.value)} /></td>
                      <td style={td}><input style={inpNum} type="number" value={l.hours_high} onChange={(e) => setField(i, 'hours_high', e.target.value)} /></td>
                      <td style={td}><input style={inpNum} type="number" value={l.rate_usd} onChange={(e) => setField(i, 'rate_usd', e.target.value)} title={l.rate_card_ref || 'Rate (firm card applied on save where matched)'} /></td>
                      <td style={td}><button style={delBtn} onClick={() => removeRow(i)} title="Remove row">✕</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <button style={addBtn} onClick={addRow}>+ Add role</button>

              <div style={contRow}>
                <label style={{ fontSize: 12, color: 'var(--fg-dim)' }}>Contingency %</label>
                <input style={inpNum} type="number" value={contingency} onChange={(e) => update(lines, Number(e.target.value) || 0)} />
              </div>

              {totals && (
                <div style={totalsBox}>
                  <div style={totalRow}><span>Subtotal</span><span>{money(totals.subtotal_low)} – {money(totals.subtotal_high)}</span></div>
                  {totals.contingency_pct ? <div style={totalRow}><span>+ Contingency {totals.contingency_pct}%</span><span /></div> : null}
                  <div style={{ ...totalRow, fontWeight: 700, color: 'var(--fg)' }}><span>Total</span><span>{money(totals.grand_low)} – {money(totals.grand_high)}</span></div>
                  {totals.adverse_sensitivity_pct ? (
                    <div style={{ ...totalRow, color: 'var(--accent)' }}><span>Worst case (+{totals.adverse_sensitivity_pct}%)</span><span>{money(totals.worst_case_low)} – {money(totals.worst_case_high)}</span></div>
                  ) : null}
                </div>
              )}

              {rateNotes.length > 0 && (
                <div style={notesBox}>
                  {rateNotes.map((n, i) => <p key={i} style={noteLine}>⚠ {n}</p>)}
                </div>
              )}
            </>
          )}
        </div>

        {!legacy && (
          <div style={footer}>
            <button onClick={onClose} style={ghostBtn} disabled={saving}>Cancel</button>
            <button onClick={save} style={primaryBtn} disabled={saving || loading}>{saving ? 'Saving…' : 'Save as new version'}</button>
          </div>
        )}
      </div>
    </div>
  );
}

const overlay: React.CSSProperties = { position: 'fixed', inset: 0, background: 'rgba(0,0,0,.4)', zIndex: 60, display: 'flex', justifyContent: 'flex-end' };
const drawer: React.CSSProperties = { width: 560, maxWidth: '96vw', height: '100%', background: 'var(--surface)', borderLeft: '1px solid var(--border)', display: 'flex', flexDirection: 'column' };
const header: React.CSSProperties = { height: 48, flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 14px', borderBottom: '1px solid var(--border)' };
const titleStyle: React.CSSProperties = { fontSize: 13, fontWeight: 600, color: 'var(--fg)', fontFamily: 'var(--font-sans)' };
const closeBtn: React.CSSProperties = { background: 'none', border: 'none', color: 'var(--fg-muted)', cursor: 'pointer', fontSize: 13 };
const hint: React.CSSProperties = { flexShrink: 0, margin: 0, padding: '10px 14px', fontSize: 11, color: 'var(--fg-muted)', lineHeight: 1.4, borderBottom: '1px solid var(--border)' };
const muted: React.CSSProperties = { fontSize: 12, color: 'var(--fg-muted)', lineHeight: 1.5, padding: '14px 0' };
const table: React.CSSProperties = { width: '100%', borderCollapse: 'collapse', fontSize: 12, marginTop: 12 };
const th: React.CSSProperties = { textAlign: 'left', padding: '6px 4px', fontSize: 9, fontFamily: 'var(--font-mono)', letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--fg-muted)', borderBottom: '1px solid var(--border)' };
const thNum: React.CSSProperties = { ...th, textAlign: 'right', width: 64 };
const td: React.CSSProperties = { padding: '3px 2px', borderBottom: '1px solid var(--border)' };
const inp: React.CSSProperties = { width: '100%', minWidth: 60, background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 6, color: 'var(--fg)', fontSize: 12, padding: '5px 6px' };
const inpNum: React.CSSProperties = { ...inp, width: 60, textAlign: 'right', fontFamily: 'var(--font-mono)' };
const delBtn: React.CSSProperties = { background: 'none', border: 'none', color: 'var(--fg-muted)', cursor: 'pointer', fontSize: 11 };
const addBtn: React.CSSProperties = { marginTop: 10, background: 'var(--surface-2)', border: '1px solid var(--border-strong)', borderRadius: 8, color: 'var(--fg-dim)', fontSize: 11, padding: '6px 12px', cursor: 'pointer' };
const contRow: React.CSSProperties = { display: 'flex', gap: 10, alignItems: 'center', marginTop: 16 };
const totalsBox: React.CSSProperties = { marginTop: 16, padding: 12, background: 'var(--surface-2)', borderRadius: 10, border: '1px solid var(--border)' };
const totalRow: React.CSSProperties = { display: 'flex', justifyContent: 'space-between', fontSize: 13, color: 'var(--fg-dim)', padding: '3px 0', fontFamily: 'var(--font-mono)' };
const notesBox: React.CSSProperties = { marginTop: 12, padding: 10, background: 'var(--accent-soft)', borderRadius: 8 };
const noteLine: React.CSSProperties = { margin: '2px 0', fontSize: 11, color: 'var(--accent)', lineHeight: 1.4 };
const footer: React.CSSProperties = { flexShrink: 0, display: 'flex', gap: 8, justifyContent: 'flex-end', padding: 14, borderTop: '1px solid var(--border)' };
const ghostBtn: React.CSSProperties = { background: 'transparent', border: '1px solid var(--border-strong)', color: 'var(--fg-dim)', borderRadius: 8, fontSize: 12, padding: '7px 14px', cursor: 'pointer' };
const primaryBtn: React.CSSProperties = { background: 'var(--accent-soft)', border: '1px solid var(--accent)', color: 'var(--accent)', borderRadius: 8, fontSize: 12, padding: '7px 14px', cursor: 'pointer' };
