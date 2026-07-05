import { useCallback, useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import {
  getPublicQuestionnaire,
  submitPublicAnswers,
  checkPublicReadiness,
  finalizePublicQuestionnaire,
  type PublicQuestion,
  type ReadinessFeedback,
} from '../services/publicQuestionnaireService';
import { themeLabel } from '../components/ui/QuestionMeta';

const roleHint = (role?: string | null): string =>
  role === 'technical' ? 'For your IT team'
  : role === 'security' ? 'For security / compliance'
  : role === 'procurement' ? 'For procurement'
  : '';

type Phase = 'loading' | 'ready' | 'invalid' | 'done';
type SaveState = 'idle' | 'saving' | 'saved' | 'error';

const READINESS_LABEL: Record<string, { text: string; pct: number }> = {
  ready: { text: 'Looks complete', pct: 100 },
  ready_with_assumptions: { text: 'Nearly there — a few assumptions remain', pct: 75 },
  needs_attention: { text: 'A few answers need detail', pct: 50 },
  needs_more_info: { text: 'More detail needed', pct: 30 },
};

export default function PublicQuestionnaire() {
  const { token } = useParams<{ token: string }>();
  const [phase, setPhase] = useState<Phase>('loading');
  const [firm, setFirm] = useState<{ name: string; logo_url: string | null; primary_color: string | null } | null>(null);
  const [questions, setQuestions] = useState<PublicQuestion[]>([]);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [prefilled, setPrefilled] = useState<Record<string, boolean>>({});
  const [respondent, setRespondent] = useState({ name: '', designation: '', email: '' });
  const [feedback, setFeedback] = useState<ReadinessFeedback | null>(null);
  const [checking, setChecking] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [saveState, setSaveState] = useState<SaveState>('idle');
  const [error, setError] = useState<string | null>(null);

  const dirtyRef = useRef(false);
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = useCallback(async () => {
    if (!token) { setPhase('invalid'); return; }
    setPhase('loading');
    try {
      const data = await getPublicQuestionnaire(token);
      setFirm(data.firm);
      setQuestions(data.questions);
      setAnswers(Object.fromEntries(data.questions.map((q) => [q.question_id, q.answer || ''])));
      setPrefilled(Object.fromEntries(data.questions.map((q) => [q.question_id, !!q.prefilled])));
      if (data.respondent) {
        setRespondent({
          name: data.respondent.name || '',
          designation: data.respondent.designation || '',
          email: data.respondent.email || '',
        });
      }
      setPhase(data.submitted_at ? 'done' : 'ready');
    } catch {
      setPhase('invalid');
    }
  }, [token]);

  useEffect(() => { void load(); }, [load]);

  const accent = firm?.primary_color || '#4f46e5';
  const filledAnswers = useCallback(
    () => Object.fromEntries(Object.entries(answers).filter(([, v]) => v.trim())),
    [answers],
  );

  // ---- Save (manual + debounced autosave) — the form is long; never lose work. ----
  const doSave = useCallback(async (): Promise<boolean> => {
    if (!token) return false;
    const payload = filledAnswers();
    if (!Object.keys(payload).length) { setSaveState('idle'); dirtyRef.current = false; return true; }
    setSaveState('saving');
    try {
      await submitPublicAnswers(token, payload);
      dirtyRef.current = false;
      setSaveState('saved');
      return true;
    } catch {
      setSaveState('error');
      return false;
    }
  }, [token, filledAnswers]);

  const onAnswerChange = (qid: string, value: string) => {
    setAnswers((p) => ({ ...p, [qid]: value }));
    dirtyRef.current = true;
    setSaveState('idle');
    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => { void doSave(); }, 1500);  // autosave
  };

  // Flush a pending save on unmount / tab hide so a close doesn't drop the last edits.
  useEffect(() => {
    const flush = () => { if (dirtyRef.current) void doSave(); };
    window.addEventListener('visibilitychange', flush);
    return () => {
      window.removeEventListener('visibilitychange', flush);
      if (saveTimer.current) clearTimeout(saveTimer.current);
      flush();
    };
  }, [doSave]);

  const check = async () => {
    if (!token) return;
    if (!Object.keys(filledAnswers()).length) { setError('Answer at least one question first.'); return; }
    setChecking(true);
    setError(null);
    try {
      setFeedback(await checkPublicReadiness(token, filledAnswers()));
      dirtyRef.current = false;
      setSaveState('saved');
    } catch (e) {
      const status = (e as { response?: { status?: number } })?.response?.status;
      setError(status === 429 ? 'You’ve checked a lot recently — give it a moment and try again.' : 'Could not check readiness right now. Please try again.');
    } finally {
      setChecking(false);
    }
  };

  const submit = async () => {
    if (!token) return;
    if (!Object.keys(filledAnswers()).length) { setError('Please answer at least one question.'); return; }
    if (!respondent.name.trim() || !respondent.email.includes('@')) {
      setError('Please add your name and a valid email below so the team knows who completed this.');
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await finalizePublicQuestionnaire(token, filledAnswers(), {
        name: respondent.name.trim(), designation: respondent.designation.trim(), email: respondent.email.trim(),
      });
      setPhase('done');
    } catch (e) {
      setError((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'Could not submit your answers. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  if (phase === 'loading') return <Shell><p style={muted}>Loading…</p></Shell>;
  if (phase === 'invalid') {
    return (
      <Shell>
        <div style={{ textAlign: 'center', padding: '24px 0' }}>
          <h1 style={h1}>This link isn’t available</h1>
          <p style={muted}>This questionnaire link is no longer valid or has been closed. Please ask your contact for a fresh link.</p>
        </div>
      </Shell>
    );
  }
  if (phase === 'done') {
    return (
      <Shell firm={firm} accent={accent}>
        <div style={{ textAlign: 'center', padding: '36px 0' }}>
          <div style={{ width: 56, height: 56, borderRadius: '50%', background: accent, color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 28, margin: '0 auto 16px' }}>✓</div>
          <h1 style={h1}>Thank you</h1>
          <p style={muted}>Your answers have been sent{firm?.name ? ` to ${firm.name}` : ''} and the team is reviewing them. You can close this page.</p>
        </div>
      </Shell>
    );
  }

  const total = questions.length;
  const answeredCount = questions.filter((q) => (answers[q.question_id] || '').trim()).length;
  const rl = feedback ? (READINESS_LABEL[feedback.readiness_status] || READINESS_LABEL.needs_more_info) : null;
  const noteFor = (qid: string) => feedback?.vague_answers.find((v) => v.question_id === qid)?.note;
  const assumptionFor = (qid: string) => feedback?.assumptions.find((a) => a.question_id === qid);

  return (
    <Shell firm={firm} accent={accent} progress={total ? answeredCount / total : 0}>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
        <h1 style={h1}>A few questions about your project</h1>
        <span style={{ fontSize: 12, color: '#9ca3af', fontWeight: 600 }}>{answeredCount} / {total} answered</span>
      </div>
      <p style={muted}>
        {firm?.name ? `${firm.name} is` : 'We’re'} scoping your project and {firm?.name ? 'needs' : 'need'} a little more
        detail to get the estimate right. Your answers save automatically — finish anytime, then check how complete it
        looks before sending.
      </p>

      {feedback && rl && (
        <div style={{ ...readinessBox, borderColor: accent }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <strong style={{ fontSize: 14 }}>{rl.text}</strong>
            <span style={{ fontSize: 12, color: '#6b7280' }}>{Math.round((feedback.readiness_score || 0) * 100)}% ready</span>
          </div>
          <div style={{ height: 6, background: '#e5e7eb', borderRadius: 999 }}>
            <div style={{ width: `${rl.pct}%`, height: 6, background: accent, borderRadius: 999, transition: 'width .3s' }} />
          </div>
          {feedback.contradictions.length > 0 && (
            <div style={{ marginTop: 12 }}>
              <p style={fbHead}>These answers may conflict — could you clarify?</p>
              {feedback.contradictions.map((c, i) => <p key={i} style={fbLine}>• {c.detail}</p>)}
            </div>
          )}
          {feedback.assumptions.length > 0 && (
            <div style={{ marginTop: 12 }}>
              <p style={fbHead}>If you leave some blank, we’ll assume:</p>
              {feedback.assumptions.map((a, i) => (
                <p key={i} style={fbLine}>• {a.assumption}{a.risk_level ? ` (${a.risk_level} risk)` : ''}</p>
              ))}
            </div>
          )}
        </div>
      )}

      <div style={{ marginTop: 24 }}>
        {questions.map((q, i) => {
          const note = noteFor(q.question_id);
          const asm = assumptionFor(q.question_id);
          const isPrefilled = prefilled[q.question_id];
          return (
            <div key={q.question_id} style={card}>
              <div style={qHead}>
                <span style={{ ...qNum, background: accent }}>{i + 1}</span>
                {q.priority === 'blocking' && <span style={impBadge}>Important</span>}
                {q.theme ? <span style={qCat}>{themeLabel(q.theme)}</span> : (q.area_or_category && <span style={qCat}>{q.area_or_category}</span>)}
                {roleHint(q.respondent_role) && <span style={roleBadge}>{roleHint(q.respondent_role)}</span>}
                {isPrefilled && <span style={prefillTag}>✎ your team started this — edit if needed</span>}
              </div>
              <p style={qText}>{q.question_text}</p>
              <textarea
                value={answers[q.question_id] || ''}
                onChange={(e) => onAnswerChange(q.question_id, e.target.value)}
                placeholder="Your answer…"
                style={textarea}
                rows={3}
              />
              {note && <p style={nudge}>💡 {note}</p>}
              {/* A dynamic readiness assumption (asm) takes precedence over the static default. */}
              {!answers[q.question_id]?.trim() && asm && <p style={nudge}>If left blank: we’ll assume “{asm.assumption}”</p>}
              {!answers[q.question_id]?.trim() && !asm && q.default_assumption && (
                <div style={defaultBox}>
                  <p style={{ margin: 0, fontSize: 12.5, color: '#374151', lineHeight: 1.45 }}>
                    <strong>Not sure?</strong> We can assume: “{q.default_assumption}”
                  </p>
                  <button
                    type="button"
                    onClick={() => onAnswerChange(q.question_id, q.default_assumption || '')}
                    style={{ ...acceptBtn, color: accent, borderColor: accent }}
                  >
                    Use this
                  </button>
                </div>
              )}
            </div>
          );
        })}
        {!questions.length && <p style={muted}>There are no open questions right now.</p>}
      </div>

      {questions.length > 0 && (
        <div style={{ ...card, marginTop: 20, background: '#fbfcfe' }}>
          <p style={{ margin: '0 0 10px', fontSize: 13, fontWeight: 600, color: '#374151' }}>Your details</p>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            <input value={respondent.name} onChange={(e) => setRespondent((p) => ({ ...p, name: e.target.value }))}
                   placeholder="Full name *" style={{ ...detailInput, flex: 1, minWidth: 160 }} />
            <input value={respondent.designation} onChange={(e) => setRespondent((p) => ({ ...p, designation: e.target.value }))}
                   placeholder="Title / role" style={{ ...detailInput, flex: 1, minWidth: 160 }} />
          </div>
          <input value={respondent.email} onChange={(e) => setRespondent((p) => ({ ...p, email: e.target.value }))}
                 placeholder="Email *" type="email" style={{ ...detailInput, width: '100%', marginTop: 10 }} />
        </div>
      )}

      {error && <p style={{ color: '#dc2626', fontSize: 13, marginTop: 12 }}>{error}</p>}

      {questions.length > 0 && (
        <div style={actionBar}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, flex: 1, minWidth: 140 }}>
            <button onClick={() => void doSave()} disabled={saveState === 'saving'} style={ghostBtn}>
              {saveState === 'saving' ? 'Saving…' : 'Save'}
            </button>
            <span style={{ fontSize: 12, color: saveState === 'error' ? '#dc2626' : '#9ca3af' }}>
              {saveState === 'saved' ? 'Saved' : saveState === 'error' ? 'Save failed — retry' : saveState === 'saving' ? '' : 'Autosaves as you type'}
            </span>
          </div>
          <button onClick={check} disabled={checking || submitting} style={{ ...secondaryBtn, borderColor: accent, color: accent }}>
            {checking ? 'Checking…' : 'Check readiness'}
          </button>
          <button onClick={submit} disabled={submitting || checking} style={{ ...submitBtn, background: accent }}>
            {submitting ? 'Sending…' : 'Send my answers'}
          </button>
        </div>
      )}
    </Shell>
  );
}

function Shell({
  children, firm, accent, progress,
}: {
  children: React.ReactNode;
  firm?: { name: string; logo_url: string | null } | null;
  accent?: string;
  progress?: number;
}) {
  const a = accent || '#4f46e5';
  return (
    <div style={page}>
      <div style={card0}>
        <div style={{ height: 4, background: a, borderTopLeftRadius: 16, borderTopRightRadius: 16 }} />
        <div style={{ padding: '24px 28px 0' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, minHeight: 36 }}>
            {firm?.logo_url ? (
              <img src={firm.logo_url} alt={firm?.name || 'Firm'} style={{ height: 34, maxWidth: 180, objectFit: 'contain' }} onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = 'none'; }} />
            ) : (
              <span style={{ fontWeight: 700, fontSize: 19, color: a }}>{firm?.name || 'Project questionnaire'}</span>
            )}
            {firm?.logo_url && firm?.name && <span style={{ fontWeight: 600, fontSize: 15, color: '#374151' }}>{firm.name}</span>}
          </div>
          {typeof progress === 'number' && (
            <div style={{ height: 4, background: '#eef2f7', borderRadius: 999, marginTop: 16 }}>
              <div style={{ width: `${Math.round(progress * 100)}%`, height: 4, background: a, borderRadius: 999, transition: 'width .3s' }} />
            </div>
          )}
        </div>
        <div style={{ padding: '20px 28px 28px' }}>{children}</div>
        <div style={footer}>
          <span>Powered by <strong style={{ color: '#111827' }}>Grounded<span style={{ color: '#34a37b' }}>IQ</span></strong></span>
          <span style={{ color: '#cbd5e1' }}>·</span>
          <span>Your answers are shared only with the team that sent you this link.</span>
        </div>
      </div>
    </div>
  );
}

const page: React.CSSProperties = { minHeight: '100dvh', background: 'linear-gradient(180deg,#eef2f9 0%,#f8fafc 240px)', color: '#111827', fontFamily: 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif', padding: '40px 16px' };
const card0: React.CSSProperties = { maxWidth: 660, margin: '0 auto', background: '#fff', borderRadius: 16, border: '1px solid #e5e7eb', boxShadow: '0 10px 40px rgba(15,23,42,.08)', overflow: 'hidden' };
const h1: React.CSSProperties = { fontSize: 23, fontWeight: 700, margin: '0 0 8px', letterSpacing: '-.01em' };
const muted: React.CSSProperties = { color: '#6b7280', fontSize: 14.5, lineHeight: 1.55, margin: 0 };
const card: React.CSSProperties = { border: '1px solid #e5e7eb', borderRadius: 12, padding: 16, marginBottom: 14, background: '#fff' };
const qHead: React.CSSProperties = { display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8, flexWrap: 'wrap' };
const qNum: React.CSSProperties = { display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 22, height: 22, borderRadius: 999, color: '#fff', fontSize: 12, fontWeight: 700, flexShrink: 0 };
const qCat: React.CSSProperties = { fontSize: 11, textTransform: 'uppercase', letterSpacing: '.06em', color: '#9ca3af', fontWeight: 600 };
const impBadge: React.CSSProperties = { fontSize: 10.5, textTransform: 'uppercase', letterSpacing: '.05em', fontWeight: 700, color: '#b91c1c', background: '#fee2e2', border: '1px solid #fecaca', borderRadius: 5, padding: '2px 7px' };
const roleBadge: React.CSSProperties = { fontSize: 10.5, textTransform: 'uppercase', letterSpacing: '.05em', color: '#6b7280', background: '#f3f4f6', border: '1px solid #e5e7eb', borderRadius: 5, padding: '2px 7px' };
const defaultBox: React.CSSProperties = { marginTop: 10, padding: '10px 12px', borderRadius: 8, background: '#f8fafc', border: '1px solid #e5e7eb', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap' };
const acceptBtn: React.CSSProperties = { background: '#fff', border: '1px solid', borderRadius: 8, padding: '6px 12px', fontSize: 12.5, fontWeight: 600, cursor: 'pointer', whiteSpace: 'nowrap' };
const prefillTag: React.CSSProperties = { fontSize: 11, color: '#6b7280', fontStyle: 'italic' };
const qText: React.CSSProperties = { fontSize: 15.5, fontWeight: 500, margin: '0 0 10px', lineHeight: 1.45, color: '#1f2937' };
const textarea: React.CSSProperties = { width: '100%', boxSizing: 'border-box', border: '1px solid #d1d5db', borderRadius: 8, padding: '10px 12px', fontSize: 14.5, fontFamily: 'inherit', resize: 'vertical', outlineColor: '#4f46e5' };
const detailInput: React.CSSProperties = { boxSizing: 'border-box', border: '1px solid #d1d5db', borderRadius: 8, padding: '9px 12px', fontSize: 14, fontFamily: 'inherit' };
const nudge: React.CSSProperties = { margin: '8px 0 0', fontSize: 12.5, color: '#92710b', lineHeight: 1.4 };
const actionBar: React.CSSProperties = { display: 'flex', gap: 10, marginTop: 18, flexWrap: 'wrap', alignItems: 'center', borderTop: '1px solid #f1f5f9', paddingTop: 16 };
const submitBtn: React.CSSProperties = { color: '#fff', border: 'none', borderRadius: 10, padding: '11px 20px', fontSize: 15, fontWeight: 600, cursor: 'pointer' };
const secondaryBtn: React.CSSProperties = { background: '#fff', border: '1px solid', borderRadius: 10, padding: '11px 18px', fontSize: 15, fontWeight: 600, cursor: 'pointer' };
const ghostBtn: React.CSSProperties = { background: '#f3f4f6', border: '1px solid #e5e7eb', color: '#374151', borderRadius: 10, padding: '11px 16px', fontSize: 14, fontWeight: 600, cursor: 'pointer' };
const readinessBox: React.CSSProperties = { marginTop: 20, padding: 16, borderRadius: 12, border: '1px solid', background: '#fafbff' };
const fbHead: React.CSSProperties = { margin: '0 0 4px', fontSize: 13, fontWeight: 600, color: '#374151' };
const fbLine: React.CSSProperties = { margin: '2px 0', fontSize: 13, color: '#4b5563', lineHeight: 1.45 };
const footer: React.CSSProperties = { display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', padding: '14px 28px', borderTop: '1px solid #f1f5f9', background: '#fbfcfe', fontSize: 12, color: '#9ca3af' };
