import { useEffect, useMemo, useRef, useState } from 'react';
import { toast } from 'react-hot-toast';
import * as presalesService from '../../services/presalesService';
import type { AnalysisAssumption } from './AnalysisStep';
import { PriorityPill, RoleChip, ThemeChip, EstimateImpact, DefaultAssumption } from '../ui/QuestionMeta';

export interface PresalesQuestion {
  question_id?: string;
  question_number?: string;
  display_order?: number;
  question_type?: 'p1' | 'p1_blocker' | 'kickstart' | string;
  question_text?: string;
  question?: string;
  blocker?: string;
  category?: string;
  priority?: string;
  area?: string;
  why_it_matters?: string;
  why_critical?: string;
  impact_if_unknown?: string;
  answer?: string | null;
  answer_quality?: string | null;
  description?: string;
  area_or_category?: string;
  impact_description?: string;
  status?: string;
  // Enterprise curation (A2)
  theme?: string | null;
  respondent_role?: string | null;
  estimate_impact?: string | null;
  default_assumption?: string | null;
  default_assumption_risk?: string | null;
}

interface QuestionsStepProps {
  presalesId: string;
  initialQuestions?: PresalesQuestion[];
  questions: PresalesQuestion[];
  setQuestions: React.Dispatch<React.SetStateAction<PresalesQuestion[]>>;
  answers: Record<string, string>;
  setAnswers: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  additionalContext: string;
  setAdditionalContext: (v: string) => void;
  onBack: () => void;
  onComplete: () => void;
  /** Assumptions from the last readiness analysis — rendered inline under the
   *  unanswered questions they cover, so "can't answer" has a visible cost. */
  assumptions?: AnalysisAssumption[];
  /** Per-answer-key "can't answer this — assume for me" marks (lifted to the
   *  flow so they survive phase changes). */
  skipped?: Record<string, boolean>;
  setSkipped?: React.Dispatch<React.SetStateAction<Record<string, boolean>>>;
  /** Scroll target (DOM anchor id) when arriving via "revise this answer". */
  focusAnchorId?: string | null;
  onFocusConsumed?: () => void;
  /** When the client clicked "Send my answers" (vs. just autosaving). Null = the
   *  client may have started (autosaved) but has NOT submitted. */
  clientSubmittedAt?: string | null;
}

const isP1 = (q: PresalesQuestion) =>
  q.question_type === 'p1' ||
  q.question_type === 'p1_blocker' ||
  Boolean(q.blocker);

const isFollowUp = (q: PresalesQuestion) => q.question_type === 'follow_up';

const HEDGE =
  /\b(not sure|unsure|idk|i\s?don'?t\s?know|dunno|no idea|tbd|to be decided|maybe|n\/?a)\b/i;

type AnswerState = 'empty' | 'thin' | 'ok';

const shareBtn = (primary: boolean): React.CSSProperties => ({
  background: primary ? 'var(--accent-soft)' : 'var(--surface)',
  border: `1px solid ${primary ? 'var(--accent)' : 'var(--border-strong)'}`,
  color: primary ? 'var(--accent)' : 'var(--fg-dim)',
  borderRadius: 8, fontSize: 12, padding: '7px 12px', cursor: 'pointer', whiteSpace: 'nowrap',
});

function answerStateFor(value: string, blocker: boolean): AnswerState {
  const v = value.trim();
  if (!v) return 'empty';
  if (blocker && (v.length < 24 || HEDGE.test(v))) return 'thin';
  return 'ok';
}

export default function QuestionsStep({
  presalesId,
  initialQuestions,
  questions,
  setQuestions,
  answers,
  setAnswers,
  additionalContext,
  setAdditionalContext,
  onBack,
  onComplete,
  assumptions,
  skipped,
  setSkipped,
  focusAnchorId,
  onFocusConsumed,
  clientSubmittedAt,
}: QuestionsStepProps) {
  const [loading, setLoading] = useState(questions.length === 0);
  const [submitting, setSubmitting] = useState(false);
  const [shareOpen, setShareOpen] = useState(false);
  const [shareLink, setShareLink] = useState<string | null>(null);
  const [clientEmail, setClientEmail] = useState('');
  const [sharing, setSharing] = useState<null | 'send' | 'remind' | 'revoke' | 'copy' | 'mark'>(null);
  const [markedShared, setMarkedShared] = useState(false);
  const linkInputRef = useRef<HTMLInputElement | null>(null);

  // Pre-mint the link as soon as the panel opens so the Copy button can write to the
  // clipboard SYNCHRONOUSLY within the click (a clipboard write after an `await`
  // loses the browser's user-activation and silently fails). The 401-refresh round
  // trip, if any, happens here in the background — not inside the copy gesture.
  useEffect(() => {
    if (!shareOpen || shareLink) return;
    let cancelled = false;
    (async () => {
      try {
        const { token } = await presalesService.createShareLink(presalesId);
        if (!cancelled) setShareLink(`${window.location.origin}/q/${token}`);
      } catch {
        /* non-fatal — Send/Copy will surface a clear error if it still fails */
      }
    })();
    return () => { cancelled = true; };
  }, [shareOpen, shareLink, presalesId]);

  // A client-answered question surfaces as status 'needs_review' (the firm reviews
  // it). Count them so we can show a "client submitted" banner.
  const clientAnswered = questions.filter(
    (q) => (q.status === 'needs_review') && Boolean((q.answer || '').trim()),
  ).length;

  const sendLink = async () => {
    if (!clientEmail.trim() || !clientEmail.includes('@')) { toast.error('Enter a valid client email'); return; }
    setSharing('send');
    try {
      const { link, emailed } = await presalesService.sendClientLink(presalesId, clientEmail.trim());
      setShareLink(link);
      toast.success(emailed ? 'Questionnaire emailed to your client' : 'Link ready (email not configured — copy it below)');
    } catch {
      toast.error('Could not send the client link');
    } finally {
      setSharing(null);
    }
  };

  const copyLink = () => {
    // Synchronous within the click — no `await` before the clipboard write (that
    // loses user-activation). Falls back to selecting the readonly input + execCommand.
    const url = shareLink;
    if (!url) { toast.error('Link not ready yet — give it a second.'); return; }
    const selectFallback = () => {
      const el = linkInputRef.current;
      if (el) {
        el.focus();
        el.select();
        try { document.execCommand('copy'); toast.success('Client link copied'); return; } catch { /* fall through */ }
      }
      toast.error('Could not copy — select the link below and copy it manually.');
    };
    if (navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(url).then(
        () => toast.success('Client link copied'),
        () => selectFallback(),
      );
    } else {
      selectFallback();
    }
  };

  const markShared = async () => {
    setSharing('mark');
    try {
      const { link } = await presalesService.markLinkShared(presalesId);
      setShareLink(link);
      setMarkedShared(true);
      toast.success('Marked as sent — this project now shows "Link sent".');
    } catch {
      toast.error('Could not mark the link as sent');
    } finally {
      setSharing(null);
    }
  };

  const remind = async () => {
    setSharing('remind');
    try {
      const { emailed } = await presalesService.sendReminder(presalesId);
      toast.success(emailed ? 'Reminder sent' : 'Reminder logged (email not configured)');
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(typeof detail === 'string' ? detail : 'Could not send a reminder');
    } finally {
      setSharing(null);
    }
  };

  const revokeLink = async () => {
    if (!window.confirm('Revoke the client link? The current URL will stop working immediately.')) return;
    setSharing('revoke');
    try {
      await presalesService.revokeShareLink(presalesId);
      setShareLink(null);
      toast.success('Client link revoked');
    } catch {
      toast.error('Could not revoke the link');
    } finally {
      setSharing(null);
    }
  };

  // Seed answers by positional bucket index (p1_0, question_0, followup_0, …),
  // matching the old frontend's contract with POST /presales/:id/questions/answers.
  const seedAnswersFromQuestions = (arr: PresalesQuestion[]) => {
    const p1Items: PresalesQuestion[] = [];
    const kItems: PresalesQuestion[] = [];
    const fItems: PresalesQuestion[] = [];
    for (const q of arr) {
      if (isP1(q)) p1Items.push(q);
      else if (isFollowUp(q)) fItems.push(q);
      else kItems.push(q);
    }
    setAnswers((prev) => {
      const seeded = { ...prev };
      p1Items.forEach((q, i) => {
        const key = `p1_${i}`;
        if (q.answer && !seeded[key]) seeded[key] = q.answer;
      });
      kItems.forEach((q, i) => {
        const key = `question_${i}`;
        if (q.answer && !seeded[key]) seeded[key] = q.answer;
      });
      fItems.forEach((q, i) => {
        const key = `followup_${i}`;
        if (q.answer && !seeded[key]) seeded[key] = q.answer;
      });
      return seeded;
    });
  };

  // Initial seed: if parent already has questions (e.g. coming back from
  // analysis), keep them. Otherwise take what the upload returned, or refetch.
  useEffect(() => {
    if (questions.length > 0) {
      setLoading(false);
      return;
    }
    const haveUsable =
      Array.isArray(initialQuestions) && initialQuestions.length > 0;

    if (haveUsable) {
      setQuestions(initialQuestions);
      seedAnswersFromQuestions(initialQuestions);
      setLoading(false);
      const needsHydrate = !initialQuestions.every((q) => Boolean(q.question_id));
      if (!needsHydrate) return;
    }

    let cancelled = false;
    (async () => {
      try {
        const data = await presalesService.getQuestions(presalesId);
        if (cancelled) return;
        const arr: PresalesQuestion[] = Array.isArray(data)
          ? data
          : Array.isArray((data as { questions?: PresalesQuestion[] })?.questions)
          ? (data as { questions: PresalesQuestion[] }).questions
          : [];
        setQuestions(arr);
        seedAnswersFromQuestions(arr);
      } catch (err) {
        console.error('Failed to load presales questions', err);
        if (!haveUsable) toast.error('Failed to load questions.');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [presalesId, initialQuestions, questions.length]);

  const { p1, kickstart, followUps } = useMemo(() => {
    const p1List: PresalesQuestion[] = [];
    const kList: PresalesQuestion[] = [];
    const fList: PresalesQuestion[] = [];
    for (const q of questions) {
      if (isP1(q)) p1List.push(q);
      else if (isFollowUp(q)) fList.push(q);
      else kList.push(q);
    }
    return { p1: p1List, kickstart: kList, followUps: fList };
  }, [questions]);

  // Assumptions keyed by the question id they cover ("P1-2" / "Q3"), so a card
  // can show what gets assumed if its question stays unanswered.
  const assumptionByQuestion = useMemo(() => {
    const map: Record<string, AnalysisAssumption> = {};
    for (const a of assumptions || []) {
      const id = (a.for_question_id || '').trim().toUpperCase();
      if (id) map[id] = a;
    }
    return map;
  }, [assumptions]);

  // "Revise this answer" arrives with a DOM anchor — scroll once, then clear.
  useEffect(() => {
    if (!focusAnchorId || loading) return;
    const el = document.getElementById(focusAnchorId);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      el.querySelector('textarea')?.focus({ preventScroll: true });
    }
    onFocusConsumed?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusAnchorId, loading]);

  const total = questions.length;
  const answered = Object.values(answers).filter((v) => v.trim()).length;
  const p1Answered = useMemo(
    () => p1.filter((_, i) => (answers[`p1_${i}`] || '').trim()).length,
    [p1, answers],
  );
  const pct = total > 0 ? Math.round((answered / total) * 100) : 0;

  const jumpToNextBlocker = () => {
    const idx = p1.findIndex((_, i) => !(answers[`p1_${i}`] || '').trim());
    if (idx < 0) return;
    const el = document.getElementById(`q-p1-${idx}`);
    el?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    el?.querySelector('textarea')?.focus({ preventScroll: true });
  };

  const handleSubmit = async () => {
    setSubmitting(true);
    try {
      // F6: submit answers keyed by question_id rather than positional index,
      // so a UI reorder can never silently cross-wire an answer to the wrong question.
      const payload: Array<{ question_id: string; answer: string }> = [];
      const pushFor = (list: PresalesQuestion[], keyPrefix: string) => {
        list.forEach((q, idx) => {
          if (!q.question_id) return;
          const answer = (answers[`${keyPrefix}_${idx}`] || '').trim();
          if (answer) payload.push({ question_id: q.question_id, answer });
        });
      };
      pushFor(p1, 'p1');
      pushFor(kickstart, 'question');
      pushFor(followUps, 'followup');

      // Always persist when there are answers OR free-text context, so the durable
      // additional_context reaches the analyzer + CRD (it used to only ride on report gen).
      if (payload.length > 0 || additionalContext.trim()) {
        await presalesService.saveAnswers(presalesId, payload, additionalContext);
      }
      onComplete();
    } catch (err) {
      console.error('Failed to save answers', err);
      toast.error('Failed to save answers.');
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '80px 24px',
        }}
      >
        <div
          style={{
            width: 28,
            height: 28,
            border: '2px solid var(--border-strong)',
            borderTopColor: 'var(--accent)',
            borderRadius: '50%',
            animation: 'spin 1s linear infinite',
          }}
        />
      </div>
    );
  }

  if (questions.length === 0) {
    return (
      <div style={{ maxWidth: 720, margin: '0 auto', padding: '40px 24px' }}>
        <p style={{ fontSize: 14, color: 'var(--fg-dim)', marginBottom: 24 }}>
          No questions returned for this presales analysis. You can proceed directly to the readiness analysis.
        </p>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
          <BackBtn onClick={onBack} />
          <PrimaryBtn onClick={onComplete}>Continue →</PrimaryBtn>
        </div>
      </div>
    );
  }

  const p1Open = p1.length - p1Answered;

  return (
    <div style={{ maxWidth: 1040, margin: '0 auto', padding: 'clamp(24px, 5vw, 40px) clamp(16px, 4vw, 28px)' }}>
      <header style={{ marginBottom: 26 }}>
        <p
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 10,
            letterSpacing: '.14em',
            textTransform: 'uppercase',
            color: 'var(--accent)',
            marginBottom: 8,
          }}
        >
          STEP 2 OF 4
        </p>
        <h1
          style={{
            fontFamily: 'var(--font-display)',
            fontSize: 'clamp(22px, 5vw, 28px)',
            fontWeight: 400,
            letterSpacing: '-.02em',
            color: 'var(--fg)',
            margin: '0 0 8px',
            maxWidth: 620,
          }}
        >
          A few questions to sharpen the scope
        </h1>
        <p style={{ fontSize: 14, color: 'var(--fg-muted)', lineHeight: 1.6, maxWidth: 620, margin: 0 }}>
          Answer what you can — the more precise your answers to the critical blockers, the tighter the
          estimate. Anything left blank becomes an explicit, reviewable assumption in the next step.
        </p>
        {clientSubmittedAt ? (
          <div style={{ marginTop: 14, padding: '10px 14px', borderRadius: 8, background: 'var(--ok-soft)', border: '1px solid var(--border)', color: 'var(--ok)', fontSize: 13 }}>
            ✓ Client submitted {clientAnswered} answer{clientAnswered === 1 ? '' : 's'} on {new Date(clientSubmittedAt).toLocaleString()} — review them below, then run the readiness analysis.
          </div>
        ) : clientAnswered > 0 ? (
          <div style={{ marginTop: 14, padding: '10px 14px', borderRadius: 8, background: 'var(--surface-2)', border: '1px solid var(--border)', color: 'var(--fg-dim)', fontSize: 13 }}>
            ✎ Your client has started filling this out ({clientAnswered} answer{clientAnswered === 1 ? '' : 's'} so far) but hasn't submitted yet — you'll see their final answers once they click "Send my answers".
          </div>
        ) : null}
        <div style={{ marginTop: 14 }}>
          <button
            onClick={() => setShareOpen((o) => !o)}
            style={{
              background: 'var(--surface-2)', border: '1px solid var(--border-strong)', borderRadius: 8,
              color: 'var(--fg-dim)', fontSize: 12, padding: '7px 13px', cursor: 'pointer',
              fontFamily: 'var(--font-mono)', letterSpacing: '.03em',
            }}
          >
            ↗ Send to client {shareOpen ? '▾' : '▸'}
          </button>
          {shareOpen && (
            <div style={{ marginTop: 10, padding: 14, border: '1px solid var(--border)', borderRadius: 10, background: 'var(--surface-2)', maxWidth: 560 }}>
              <p style={{ margin: '0 0 8px', fontSize: 12, color: 'var(--fg-muted)', lineHeight: 1.5 }}>
                Email your client a no-login link to answer these questions and self-check readiness. Their answers come back here for your review. Org blocks the link? Fill it on their behalf during a call, then revoke.
              </p>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                <input
                  type="email"
                  value={clientEmail}
                  onChange={(e) => setClientEmail(e.target.value)}
                  placeholder="client@company.com"
                  style={{ flex: 1, minWidth: 180, background: 'var(--surface)', border: '1px solid var(--border-strong)', borderRadius: 8, color: 'var(--fg)', fontSize: 13, padding: '7px 10px' }}
                />
                <button onClick={sendLink} disabled={!!sharing} style={shareBtn(true)}>{sharing === 'send' ? 'Sending…' : 'Send'}</button>
                <button onClick={copyLink} disabled={!!sharing} style={shareBtn(false)}>{sharing === 'copy' ? '…' : 'Copy link'}</button>
                <button onClick={markShared} disabled={!!sharing} style={shareBtn(false)} title="Mark as sent when you've shared the link yourself (e.g. email blocked)">{sharing === 'mark' ? '…' : markedShared ? '✓ Marked sent' : 'Mark sent'}</button>
                <button onClick={remind} disabled={!!sharing} style={shareBtn(false)}>{sharing === 'remind' ? '…' : 'Remind'}</button>
                <button onClick={revokeLink} disabled={!!sharing} style={shareBtn(false)}>{sharing === 'revoke' ? '…' : 'Revoke'}</button>
              </div>
              {shareLink && (
                <input
                  ref={linkInputRef}
                  readOnly
                  value={shareLink}
                  onFocus={(e) => e.currentTarget.select()}
                  style={{ marginTop: 8, width: '100%', boxSizing: 'border-box', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8, color: 'var(--fg-dim)', fontSize: 11, fontFamily: 'var(--font-mono)', padding: '6px 8px' }}
                />
              )}
            </div>
          )}
        </div>
      </header>

      <div className="np-questions">
        {/* ── Questions column ── */}
        <main style={{ minWidth: 0 }}>
          {p1.length > 0 && (
            <QuestionGroup
              eyebrow={`BLOCKING · ${p1.length} CRITICAL`}
              note="Answer or accept a default before generating — these move the estimate most"
              accent="var(--danger)"
              questions={p1}
              numberPrefix="P1"
              keyPrefix="p1"
              anchorPrefix="p1"
              answers={answers}
              setAnswers={setAnswers}
              assumptionByQuestion={assumptionByQuestion}
              skipped={skipped}
              setSkipped={setSkipped}
            />
          )}
          {followUps.length > 0 && (
            <QuestionGroup
              eyebrow={`FOLLOW-UPS · ${followUps.length} FROM YOUR ANSWERS`}
              note="Your answers raised these — quick to settle now"
              accent="var(--warn)"
              questions={followUps}
              numberPrefix="F"
              keyPrefix="followup"
              anchorPrefix="f"
              answers={answers}
              setAnswers={setAnswers}
              assumptionByQuestion={assumptionByQuestion}
              skipped={skipped}
              setSkipped={setSkipped}
            />
          )}
          {kickstart.length > 0 && (
            <QuestionGroup
              eyebrow={`CLARIFYING · ${kickstart.length} ITEMS`}
              note="Sharpen the plan — each has a smart default you can accept"
              accent="var(--accent)"
              questions={kickstart}
              numberPrefix="Q"
              keyPrefix="question"
              anchorPrefix="q"
              answers={answers}
              setAnswers={setAnswers}
              assumptionByQuestion={assumptionByQuestion}
              skipped={skipped}
              setSkipped={setSkipped}
            />
          )}

          <div
            style={{
              marginTop: 4,
              padding: 18,
              background: 'var(--surface)',
              border: '1px solid var(--border)',
              borderRadius: 12,
            }}
          >
            <p
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 9,
                color: 'var(--fg-muted)',
                letterSpacing: '.1em',
                textTransform: 'uppercase',
                marginBottom: 9,
              }}
            >
              ADDITIONAL CONTEXT — OPTIONAL
            </p>
            <textarea
              value={additionalContext}
              onChange={(e) => setAdditionalContext(e.target.value)}
              placeholder="Notes from client calls, emails, Slack threads, or any context not in the document…"
              rows={3}
              style={{
                width: '100%',
                background: 'var(--surface-2)',
                border: '1px solid var(--border)',
                borderRadius: 8,
                padding: '10px 12px',
                color: 'var(--fg)',
                fontSize: 13,
                fontFamily: 'var(--font-sans)',
                resize: 'vertical',
                outline: 'none',
                lineHeight: 1.55,
              }}
            />
          </div>
        </main>

        {/* ── Sticky summary rail ── */}
        <aside className="np-questions__rail">
          <div
            style={{
              background: 'var(--surface)',
              border: '1px solid var(--border)',
              borderRadius: 14,
              padding: '18px 18px 16px',
            }}
          >
            <p
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 9,
                letterSpacing: '.14em',
                textTransform: 'uppercase',
                color: 'var(--fg-muted)',
                margin: '0 0 10px',
              }}
            >
              PROGRESS
            </p>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 6, marginBottom: 12 }}>
              <span
                style={{
                  fontFamily: 'var(--font-display)',
                  fontSize: 34,
                  letterSpacing: '-.02em',
                  color: 'var(--fg)',
                  lineHeight: 1,
                }}
              >
                {answered}
              </span>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg-muted)' }}>
                / {total} answered
              </span>
            </div>
            <div
              style={{
                height: 6,
                background: 'var(--surface-2)',
                borderRadius: 3,
                overflow: 'hidden',
                marginBottom: 16,
              }}
            >
              <div
                style={{
                  height: '100%',
                  width: `${pct}%`,
                  background: 'linear-gradient(90deg, var(--accent), var(--accent-2))',
                  borderRadius: 3,
                  transition: 'width .4s ease',
                }}
              />
            </div>

            {p1.length > 0 && (
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: 8,
                  padding: '10px 12px',
                  borderRadius: 9,
                  background: p1Open > 0 ? 'color-mix(in oklab, var(--danger) 8%, transparent)' : 'color-mix(in oklab, var(--ok) 10%, transparent)',
                  border: `1px solid ${p1Open > 0 ? 'color-mix(in oklab, var(--danger) 26%, transparent)' : 'color-mix(in oklab, var(--ok) 26%, transparent)'}`,
                }}
              >
                <div>
                  <p
                    style={{
                      fontSize: 12.5,
                      color: 'var(--fg)',
                      margin: 0,
                      fontWeight: 500,
                    }}
                  >
                    Critical blockers
                  </p>
                  <p style={{ fontSize: 11, color: 'var(--fg-muted)', margin: '2px 0 0' }}>
                    {p1Answered} of {p1.length} answered
                  </p>
                </div>
                {p1Open > 0 ? (
                  <button
                    type="button"
                    onClick={jumpToNextBlocker}
                    style={{
                      flexShrink: 0,
                      padding: '5px 10px',
                      borderRadius: 7,
                      border: 'none',
                      background: 'var(--danger)',
                      color: '#fff',
                      fontSize: 11.5,
                      fontWeight: 500,
                      cursor: 'pointer',
                      fontFamily: 'var(--font-sans)',
                    }}
                  >
                    Next →
                  </button>
                ) : (
                  <svg width="18" height="18" fill="none" stroke="var(--ok)" viewBox="0 0 24 24">
                    <path d="M5 13l4 4L19 7" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                )}
              </div>
            )}
          </div>

          <div
            style={{
              background: 'var(--surface)',
              border: '1px solid var(--border)',
              borderRadius: 14,
              padding: '14px 16px',
            }}
          >
            <p
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 9,
                letterSpacing: '.12em',
                textTransform: 'uppercase',
                color: 'var(--fg-muted)',
                margin: '0 0 6px',
              }}
            >
              WHAT HAPPENS NEXT
            </p>
            <p style={{ fontSize: 12, color: 'var(--fg-dim)', lineHeight: 1.55, margin: 0 }}>
              We score readiness and turn every gap into an explicit assumption you can review and edit —
              nothing is guessed silently.
            </p>
          </div>

          <div style={{ display: 'flex', gap: 10, marginTop: 2 }}>
            <BackBtn onClick={onBack} />
            <PrimaryBtn onClick={handleSubmit} disabled={submitting} grow>
              {submitting ? 'Saving…' : 'Save & Analyse →'}
            </PrimaryBtn>
          </div>
        </aside>
      </div>
    </div>
  );
}

interface QuestionGroupProps {
  eyebrow: string;
  note?: string;
  accent: string;
  questions: PresalesQuestion[];
  numberPrefix: string;
  keyPrefix: string;
  anchorPrefix: string;
  answers: Record<string, string>;
  setAnswers: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  assumptionByQuestion?: Record<string, AnalysisAssumption>;
  skipped?: Record<string, boolean>;
  setSkipped?: React.Dispatch<React.SetStateAction<Record<string, boolean>>>;
}

function QuestionGroup({
  eyebrow,
  note,
  accent,
  questions,
  numberPrefix,
  keyPrefix,
  anchorPrefix,
  answers,
  setAnswers,
  assumptionByQuestion,
  skipped,
  setSkipped,
}: QuestionGroupProps) {
  return (
    <div style={{ marginBottom: 26 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 10,
            color: accent,
            letterSpacing: '.1em',
            textTransform: 'uppercase',
          }}
        >
          {eyebrow}
        </span>
        {note && <span style={{ fontSize: 12, color: 'var(--fg-muted)' }}>— {note}</span>}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {questions.map((q, idx) => {
          const answerKey = `${keyPrefix}_${idx}`;
          const displayId = (q.question_number || `${numberPrefix}-${idx + 1}`).toUpperCase();
          return (
            <QuestionCard
              key={q.question_id || `${numberPrefix}-${idx}`}
              anchorId={`q-${anchorPrefix}-${idx}`}
              question={q}
              answerKey={answerKey}
              numberPrefix={numberPrefix}
              displayNumber={idx + 1}
              accent={accent}
              answers={answers}
              setAnswers={setAnswers}
              assumption={assumptionByQuestion?.[displayId]}
              isSkipped={Boolean(skipped?.[answerKey])}
              onToggleSkip={
                setSkipped
                  ? () => setSkipped((s) => ({ ...s, [answerKey]: !s[answerKey] }))
                  : undefined
              }
            />
          );
        })}
      </div>
    </div>
  );
}

interface QuestionCardProps {
  anchorId: string;
  question: PresalesQuestion;
  answerKey: string;
  numberPrefix: string;
  displayNumber: number;
  accent: string;
  answers: Record<string, string>;
  setAnswers: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  assumption?: AnalysisAssumption;
  isSkipped?: boolean;
  onToggleSkip?: () => void;
}

function QuestionCard({
  anchorId,
  question: q,
  answerKey,
  numberPrefix,
  displayNumber,
  accent,
  answers,
  setAnswers,
  assumption,
  isSkipped,
  onToggleSkip,
}: QuestionCardProps) {
  const value = answers[answerKey] || '';
  const isBlocker = numberPrefix === 'P1';
  const state = answerStateFor(value, isBlocker);
  const hasAssumption = value.includes('[SYSTEM ASSUMPTION]');
  const skippedNoAnswer = Boolean(isSkipped) && state === 'empty';

  const headline = q.blocker || q.question_text || q.question || 'Question';
  const ask = q.blocker ? q.question_text || q.question || '' : '';
  const why = q.why_critical || q.why_it_matters || '';
  const impact = q.impact_if_unknown || q.impact_description || '';
  const showImpact = Boolean(impact) && impact !== why;
  const category = q.category || q.area || q.area_or_category || '';

  const borderColor =
    state === 'ok'
      ? 'color-mix(in oklab, var(--ok) 26%, transparent)'
      : isBlocker
      ? 'color-mix(in oklab, var(--danger) 22%, transparent)'
      : 'var(--border)';

  return (
    <div
      id={anchorId}
      style={{
        border: `1px solid ${borderColor}`,
        borderRadius: 12,
        background: isBlocker ? 'color-mix(in oklab, var(--danger) 4%, var(--surface))' : 'var(--surface)',
        overflow: 'hidden',
        transition: 'border-color .2s',
      }}
    >
      <div style={{ padding: '14px 16px 10px', display: 'flex', gap: 10, alignItems: 'flex-start' }}>
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 9,
            letterSpacing: '.08em',
            padding: '4px 7px',
            borderRadius: 6,
            background: 'var(--surface-2)',
            color: accent,
            border: `1px solid ${borderColor}`,
            flexShrink: 0,
            whiteSpace: 'nowrap',
            marginTop: 1,
          }}
        >
          {numberPrefix}-{displayNumber}
        </span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <p
            style={{
              fontSize: 14.5,
              fontWeight: isBlocker ? 600 : 500,
              color: 'var(--fg)',
              margin: 0,
              lineHeight: 1.4,
            }}
          >
            {headline}
          </p>
          {ask && (
            <p style={{ fontSize: 13, color: 'var(--fg-dim)', lineHeight: 1.5, margin: '5px 0 0' }}>{ask}</p>
          )}
          {why && (
            <p style={{ fontSize: 12.5, color: 'var(--fg-muted)', lineHeight: 1.5, margin: '5px 0 0' }}>
              {why}
            </p>
          )}
          <EstimateImpact text={q.estimate_impact} />
          {showImpact && (
            <div
              style={{
                display: 'flex',
                gap: 7,
                marginTop: 9,
                padding: '7px 10px',
                borderRadius: 8,
                background: 'var(--surface-2)',
                border: '1px solid var(--border)',
              }}
            >
              <svg
                width="13"
                height="13"
                fill="none"
                stroke={accent}
                viewBox="0 0 24 24"
                style={{ flexShrink: 0, marginTop: 1 }}
              >
                <path
                  d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0zM12 9v4M12 17h.01"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
              <p style={{ fontSize: 11.5, color: 'var(--fg-muted)', lineHeight: 1.45, margin: 0 }}>
                <span style={{ color: accent, fontWeight: 500 }}>If unanswered: </span>
                {impact}
              </p>
            </div>
          )}
          <div style={{ display: 'flex', gap: 5, marginTop: 9, flexWrap: 'wrap', alignItems: 'center' }}>
            <PriorityPill priority={q.priority || (isBlocker ? 'blocking' : 'clarifying')} />
            {q.theme ? <ThemeChip theme={q.theme} /> : (category ? <MetaTag>{category}</MetaTag> : null)}
            <RoleChip role={q.respondent_role} />
            {hasAssumption && (
              <span
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: 9,
                  letterSpacing: '.08em',
                  padding: '3px 7px',
                  borderRadius: 5,
                  background: 'color-mix(in oklab, var(--warn) 12%, transparent)',
                  color: 'var(--warn)',
                  border: '1px solid color-mix(in oklab, var(--warn) 30%, transparent)',
                  textTransform: 'uppercase',
                }}
              >
                Assumption applied
              </span>
            )}
          </div>
        </div>
        <StatusPill state={state} blocker={isBlocker} skipped={skippedNoAnswer} />
      </div>
      <div style={{ padding: '0 16px 14px' }}>
        <textarea
          value={value}
          onChange={(e) => setAnswers((p) => ({ ...p, [answerKey]: e.target.value }))}
          placeholder={
            skippedNoAnswer
              ? 'Marked "can’t answer" — we’ll make an explicit assumption you can review.'
              : isBlocker
              ? 'Be specific — this one moves the estimate…'
              : 'Provide your answer here…'
          }
          rows={2}
          style={{
            width: '100%',
            background: 'var(--surface-2)',
            border: `1px solid ${
              state === 'ok'
                ? 'color-mix(in oklab, var(--ok) 30%, transparent)'
                : 'var(--border)'
            }`,
            borderRadius: 8,
            padding: '10px 12px',
            color: 'var(--fg)',
            fontSize: 13,
            fontFamily: 'var(--font-sans)',
            resize: 'vertical',
            outline: 'none',
            transition: 'border-color .2s',
            lineHeight: 1.55,
          }}
        />
        {state === 'thin' && (
          <p
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 5,
              fontSize: 11.5,
              color: 'var(--warn)',
              margin: '7px 2px 0',
              lineHeight: 1.4,
            }}
          >
            <svg width="12" height="12" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <circle cx="12" cy="12" r="10" strokeWidth="1.8" />
              <path d="M12 8v4M12 16h.01" strokeWidth="1.8" strokeLinecap="round" />
            </svg>
            Critical blocker — a fuller answer sharpens the estimate and cuts assumptions.
          </p>
        )}
        {onToggleSkip && state === 'empty' && (
          <button
            type="button"
            onClick={onToggleSkip}
            style={{
              marginTop: 8,
              padding: '5px 10px',
              borderRadius: 7,
              border: `1px solid ${skippedNoAnswer ? 'color-mix(in oklab, var(--warn) 40%, transparent)' : 'var(--border)'}`,
              background: skippedNoAnswer ? 'color-mix(in oklab, var(--warn) 10%, transparent)' : 'transparent',
              color: skippedNoAnswer ? 'var(--warn)' : 'var(--fg-muted)',
              fontSize: 11.5,
              cursor: 'pointer',
              fontFamily: 'var(--font-sans)',
            }}
          >
            {skippedNoAnswer ? '✓ Will be assumed — undo' : 'I can’t answer this — assume for me'}
          </button>
        )}
        {state === 'empty' && !assumption && q.default_assumption && (
          <DefaultAssumption
            text={q.default_assumption}
            risk={q.default_assumption_risk}
            onAccept={() => setAnswers((p) => ({ ...p, [answerKey]: q.default_assumption || '' }))}
            onOverride={() => {
              const el = document.getElementById(anchorId)?.querySelector('textarea') as HTMLTextAreaElement | null;
              el?.focus();
            }}
          />
        )}
        {state === 'empty' && assumption && (
          <div
            style={{
              display: 'flex',
              gap: 7,
              marginTop: 9,
              padding: '8px 11px',
              borderRadius: 8,
              background: 'color-mix(in oklab, var(--warn) 7%, transparent)',
              border: '1px solid color-mix(in oklab, var(--warn) 24%, transparent)',
            }}
          >
            <span
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 9,
                letterSpacing: '.06em',
                color: 'var(--warn)',
                textTransform: 'uppercase',
                flexShrink: 0,
                marginTop: 2,
              }}
            >
              We’ll assume
            </span>
            <div style={{ minWidth: 0 }}>
              <p style={{ fontSize: 12.5, color: 'var(--fg)', lineHeight: 1.5, margin: 0 }}>
                {assumption.assumption || assumption.text}
              </p>
              {(assumption.risk_level || assumption.impact_if_wrong) && (
                <p style={{ fontSize: 11, color: 'var(--fg-muted)', lineHeight: 1.45, margin: '3px 0 0' }}>
                  {assumption.risk_level ? `${assumption.risk_level} risk` : ''}
                  {assumption.risk_level && assumption.impact_if_wrong ? ' · ' : ''}
                  {assumption.impact_if_wrong ? `If wrong: ${assumption.impact_if_wrong}` : ''}
                </p>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function StatusPill({ state, blocker, skipped }: { state: AnswerState; blocker: boolean; skipped?: boolean }) {
  const cfg =
    state === 'ok'
      ? { color: 'var(--ok)', label: 'Answered', dot: true }
      : skipped
      ? { color: 'var(--warn)', label: 'Will assume', dot: false }
      : state === 'thin'
      ? { color: 'var(--warn)', label: 'Thin', dot: false }
      : blocker
      ? { color: 'var(--danger)', label: 'Open', dot: false }
      : { color: 'var(--fg-muted)', label: 'Optional', dot: false };
  return (
    <span
      style={{
        flexShrink: 0,
        display: 'inline-flex',
        alignItems: 'center',
        gap: 4,
        fontFamily: 'var(--font-mono)',
        fontSize: 9,
        letterSpacing: '.08em',
        textTransform: 'uppercase',
        color: cfg.color,
        marginTop: 2,
      }}
    >
      {cfg.dot ? (
        <svg width="12" height="12" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path d="M5 13l4 4L19 7" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      ) : (
        <span
          style={{
            width: 6,
            height: 6,
            borderRadius: '50%',
            background: cfg.color,
            display: 'inline-block',
          }}
        />
      )}
      {cfg.label}
    </span>
  );
}

function MetaTag({ children }: { children: React.ReactNode }) {
  return (
    <span
      style={{
        fontFamily: 'var(--font-mono)',
        fontSize: 9,
        letterSpacing: '.08em',
        padding: '3px 7px',
        borderRadius: 5,
        background: 'var(--surface-2)',
        color: 'var(--fg-muted)',
        border: '1px solid var(--border)',
        textTransform: 'uppercase',
      }}
    >
      {children}
    </span>
  );
}

function BackBtn({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        padding: '11px 16px',
        borderRadius: 10,
        background: 'transparent',
        border: '1px solid var(--border-strong)',
        color: 'var(--fg-dim)',
        fontFamily: 'var(--font-sans)',
        fontSize: 13,
        cursor: 'pointer',
        flexShrink: 0,
      }}
    >
      ← Back
    </button>
  );
}

function PrimaryBtn({
  onClick,
  disabled,
  grow,
  children,
}: {
  onClick: () => void;
  disabled?: boolean;
  grow?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      style={{
        flex: grow ? 1 : undefined,
        padding: '11px 18px',
        borderRadius: 10,
        background: disabled ? 'var(--surface-2)' : 'var(--accent)',
        color: disabled ? 'var(--fg-muted)' : 'var(--accent-ink)',
        border: 'none',
        fontFamily: 'var(--font-display)',
        fontSize: 13.5,
        fontWeight: 500,
        cursor: disabled ? 'not-allowed' : 'pointer',
        boxShadow: disabled ? 'none' : 'var(--glow)',
      }}
    >
      {children}
    </button>
  );
}
