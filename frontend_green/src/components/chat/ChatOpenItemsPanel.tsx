import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'react-hot-toast';
import { notifyError } from '../../services/api';
import * as presalesService from '../../services/presalesService';
import type { PresalesQuestion } from '../../services/presalesService';
import { regenerateReport } from '../../services/chatActionsService';
import { PriorityPill, RoleChip, ThemeChip, DefaultAssumption } from '../ui/QuestionMeta';

/**
 * The in-chat "answer more → regenerate a better report" loop (B2). After the report
 * exists, the clarifying questions don't die — the still-open ones (blocking first)
 * live here. Answering one and regenerating routes through the SAME single regenerate
 * entry point as the changes queue, so the contract pipeline *evolves* the report.
 */
interface Props {
  presalesId?: string | null;
  chatHistoryId: string;
  open: boolean;
  onClose: () => void;
}

export default function ChatOpenItemsPanel({ presalesId, chatHistoryId, open, onClose }: Props) {
  const navigate = useNavigate();
  const [questions, setQuestions] = useState<PresalesQuestion[]>([]);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!presalesId) return;
    setLoading(true);
    try {
      const data = await presalesService.getQuestions(presalesId);
      const arr: PresalesQuestion[] = Array.isArray(data)
        ? data
        : Array.isArray((data as { questions?: PresalesQuestion[] })?.questions)
        ? (data as { questions: PresalesQuestion[] }).questions
        : [];
      setQuestions(arr);
    } catch {
      /* non-fatal */
    } finally {
      setLoading(false);
    }
  }, [presalesId]);

  useEffect(() => {
    if (open) { setAnswers({}); void load(); }
  }, [open, load]);

  // Still-open items (no answer), blocking first — that's already the display_order.
  const openItems = useMemo(
    () => questions.filter(
      (q) => (q.status || '') !== 'invalid' && !((q.answer || '').trim()),
    ),
    [questions],
  );

  const filledCount = Object.values(answers).filter((v) => v.trim()).length;

  const saveAndRegenerate = async () => {
    if (!presalesId) return;
    const payload = openItems
      .filter((q) => q.question_id && (answers[q.question_id] || '').trim())
      .map((q) => ({ question_id: q.question_id as string, answer: answers[q.question_id as string].trim() }));
    if (!payload.length) return;
    setBusy(true);
    try {
      await presalesService.saveAnswers(presalesId, payload);
      await regenerateReport(chatHistoryId);
      toast.success('Regenerating — the report will evolve with your new answers…');
      navigate(`/full-pipeline/${chatHistoryId}`);
    } catch (err) {
      notifyError(err, 'Could not start regeneration');
      setBusy(false);
    }
  };

  if (!open) return null;

  return (
    <div style={overlay} onClick={onClose}>
      <div style={drawer} onClick={(e) => e.stopPropagation()}>
        <div style={header}>
          <span style={titleStyle}>Open questions ({openItems.length})</span>
          <button onClick={onClose} style={closeBtn} title="Close">✕</button>
        </div>

        <div style={{ flex: 1, overflowY: 'auto', padding: 14 }}>
          {!presalesId ? (
            <p style={muted}>Open questions aren't available for this project.</p>
          ) : loading ? (
            <p style={muted}>Loading…</p>
          ) : openItems.length === 0 ? (
            <p style={muted}>Everything's answered. Nothing left to clarify — the report is running on your confirmed answers.</p>
          ) : (
            <>
              <p style={{ ...muted, marginBottom: 12 }}>
                These are still open — the report is running on a default/assumption for each. Answer any of
                them and regenerate to sharpen it.
              </p>
              {openItems.map((q) => {
                const qid = q.question_id as string;
                const val = answers[qid] || '';
                return (
                  <div key={qid} style={itemCard}>
                    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center', marginBottom: 6 }}>
                      <span style={numChip}>{(q.question_number || '').toUpperCase()}</span>
                      <PriorityPill priority={q.priority || (q.question_type === 'p1_blocker' ? 'blocking' : 'clarifying')} />
                      {q.theme ? <ThemeChip theme={q.theme} /> : null}
                      <RoleChip role={q.respondent_role} />
                    </div>
                    <p style={qTextStyle}>{q.title || q.question_text}</p>
                    <textarea
                      value={val}
                      onChange={(e) => setAnswers((p) => ({ ...p, [qid]: e.target.value }))}
                      placeholder="Answer to sharpen the report…"
                      rows={2}
                      style={textarea}
                    />
                    {!val.trim() && q.default_assumption && (
                      <DefaultAssumption
                        text={q.default_assumption}
                        risk={q.default_assumption_risk}
                        onAccept={() => setAnswers((p) => ({ ...p, [qid]: q.default_assumption || '' }))}
                      />
                    )}
                  </div>
                );
              })}
            </>
          )}
        </div>

        <div style={footer}>
          <button
            onClick={saveAndRegenerate}
            disabled={busy || filledCount === 0}
            style={{ ...regenBtn, opacity: busy || filledCount === 0 ? 0.5 : 1 }}
          >
            {busy ? 'Starting…' : `Answer ${filledCount || ''} & regenerate →`}
          </button>
        </div>
      </div>
    </div>
  );
}

const overlay: React.CSSProperties = {
  position: 'fixed', inset: 0, background: 'rgba(0,0,0,.4)', zIndex: 60,
  display: 'flex', justifyContent: 'flex-end',
};
const drawer: React.CSSProperties = {
  width: 420, maxWidth: '92vw', height: '100%', background: 'var(--surface)',
  borderLeft: '1px solid var(--border)', display: 'flex', flexDirection: 'column',
  animation: 'slideIn .15s ease',
};
const header: React.CSSProperties = {
  height: 48, flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'space-between',
  padding: '0 14px', borderBottom: '1px solid var(--border)',
};
const titleStyle: React.CSSProperties = { fontSize: 13, fontWeight: 600, color: 'var(--fg)', fontFamily: 'var(--font-sans)' };
const closeBtn: React.CSSProperties = { background: 'none', border: 'none', color: 'var(--fg-muted)', cursor: 'pointer', fontSize: 13 };
const muted: React.CSSProperties = { fontSize: 12.5, color: 'var(--fg-muted)', lineHeight: 1.55 };
const itemCard: React.CSSProperties = {
  padding: '12px 0', borderBottom: '1px solid var(--border)',
};
const numChip: React.CSSProperties = {
  fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '.06em', padding: '2px 6px', borderRadius: 5,
  background: 'var(--surface-2)', color: 'var(--fg-muted)', border: '1px solid var(--border)',
};
const qTextStyle: React.CSSProperties = { fontSize: 13.5, color: 'var(--fg)', lineHeight: 1.45, margin: '0 0 8px', fontWeight: 500 };
const textarea: React.CSSProperties = {
  width: '100%', background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 8,
  color: 'var(--fg)', fontSize: 12.5, fontFamily: 'var(--font-sans)', padding: 8, resize: 'vertical', boxSizing: 'border-box',
};
const footer: React.CSSProperties = {
  flexShrink: 0, display: 'flex', gap: 8, padding: 14, borderTop: '1px solid var(--border)',
};
const regenBtn: React.CSSProperties = {
  flex: 1, background: 'var(--accent)', color: 'var(--accent-ink)', border: 'none', borderRadius: 8,
  fontSize: 12.5, fontWeight: 600, padding: '9px', cursor: 'pointer',
};
