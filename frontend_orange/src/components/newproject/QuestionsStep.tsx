import { useEffect, useMemo, useState } from 'react';
import { toast } from 'react-hot-toast';
import * as presalesService from '../../services/presalesService';

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
  status?: string;
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
}

const isP1 = (q: PresalesQuestion) =>
  q.question_type === 'p1' ||
  q.question_type === 'p1_blocker' ||
  Boolean(q.blocker);

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
}: QuestionsStepProps) {
  const [loading, setLoading] = useState(questions.length === 0);
  const [submitting, setSubmitting] = useState(false);

  // Seed answers by positional bucket index (p1_0, question_0, …), matching
  // the old frontend's contract with POST /presales/:id/questions/answers.
  const seedAnswersFromQuestions = (arr: PresalesQuestion[]) => {
    const p1Items: PresalesQuestion[] = [];
    const kItems: PresalesQuestion[] = [];
    for (const q of arr) {
      if (isP1(q)) p1Items.push(q);
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
      // If upload payload lacked question_id we'll still hydrate via getQuestions
      // below so we have UUIDs available for any future per-question action.
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

  const { p1, kickstart } = useMemo(() => {
    const p1List: PresalesQuestion[] = [];
    const kList: PresalesQuestion[] = [];
    for (const q of questions) {
      if (isP1(q)) p1List.push(q);
      else kList.push(q);
    }
    return { p1: p1List, kickstart: kList };
  }, [questions]);

  const total = questions.length;
  const answered = Object.values(answers).filter((v) => v.trim()).length;

  const handleSubmit = async () => {
    setSubmitting(true);
    try {
      const payload: Record<string, string> = {};
      Object.entries(answers).forEach(([k, v]) => {
        if (v.trim()) payload[k] = v.trim();
      });
      if (Object.keys(payload).length > 0) {
        await presalesService.saveAnswers(presalesId, payload);
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

  return (
    <div style={{ maxWidth: 720, margin: '0 auto', padding: '40px 24px' }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          marginBottom: 22,
          gap: 16,
        }}
      >
        <div>
          <p
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 10,
              letterSpacing: '.14em',
              textTransform: 'uppercase',
              color: 'var(--accent)',
              marginBottom: 6,
            }}
          >
            STEP 2 OF 4
          </p>
          <h1
            style={{
              fontFamily: 'var(--font-display)',
              fontSize: 26,
              fontWeight: 400,
              letterSpacing: '-.02em',
              color: 'var(--fg)',
              marginBottom: 6,
            }}
          >
            Answer the questions
          </h1>
          <p style={{ fontSize: 13, color: 'var(--fg-muted)', lineHeight: 1.5 }}>
            Answer what you can. Anything left blank can be auto-filled with assumptions in the next step.
          </p>
        </div>
        <div
          style={{
            flexShrink: 0,
            padding: '10px 14px',
            background: 'var(--surface)',
            border: '1px solid var(--border)',
            borderRadius: 10,
            textAlign: 'center',
            minWidth: 80,
          }}
        >
          <p
            style={{
              fontFamily: 'var(--font-display)',
              fontSize: 28,
              color: 'var(--fg)',
              letterSpacing: '-.02em',
              lineHeight: 1,
            }}
          >
            {answered}
          </p>
          <p
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 9,
              color: 'var(--fg-muted)',
              letterSpacing: '.06em',
              textTransform: 'uppercase',
              marginTop: 2,
            }}
          >
            / {total} answered
          </p>
        </div>
      </div>

      <div
        style={{
          height: 3,
          background: 'var(--border)',
          borderRadius: 2,
          marginBottom: 28,
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            height: '100%',
            width: total > 0 ? `${(answered / total) * 100}%` : '0%',
            background: 'linear-gradient(90deg, var(--accent), var(--accent-2))',
            borderRadius: 2,
            transition: 'width .4s ease',
          }}
        />
      </div>

      {p1.length > 0 && (
        <QuestionGroup
          title={`P1 BLOCKERS · ${p1.length} CRITICAL`}
          subtitle="Must answer before report generation"
          accent="var(--danger)"
          softBg="rgba(255,106,106,.03)"
          borderColor="rgba(255,106,106,.2)"
          questions={p1}
          startIndex={1}
          numberPrefix="P1"
          answers={answers}
          setAnswers={setAnswers}
        />
      )}
      {kickstart.length > 0 && (
        <QuestionGroup
          title={`KICKSTART QUESTIONS · ${kickstart.length} ITEMS`}
          accent="var(--accent)"
          softBg="var(--surface)"
          borderColor="var(--border)"
          questions={kickstart}
          startIndex={1}
          numberPrefix="Q"
          answers={answers}
          setAnswers={setAnswers}
        />
      )}

      <div
        style={{
          marginBottom: 28,
          padding: 16,
          background: 'var(--surface)',
          border: '1px solid var(--border)',
          borderRadius: 10,
        }}
      >
        <p
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 9,
            color: 'var(--fg-muted)',
            letterSpacing: '.1em',
            textTransform: 'uppercase',
            marginBottom: 8,
          }}
        >
          ADDITIONAL CONTEXT (optional)
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
            borderRadius: 7,
            padding: '9px 11px',
            color: 'var(--fg)',
            fontSize: 13,
            fontFamily: 'var(--font-sans)',
            resize: 'vertical',
            outline: 'none',
          }}
        />
      </div>

      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 24 }}>
        <BackBtn onClick={onBack} />
        <PrimaryBtn onClick={handleSubmit} disabled={submitting}>
          {submitting ? 'Saving…' : 'Save & Analyse →'}
        </PrimaryBtn>
      </div>
    </div>
  );
}

interface QuestionGroupProps {
  title: string;
  subtitle?: string;
  accent: string;
  softBg: string;
  borderColor: string;
  questions: PresalesQuestion[];
  startIndex: number;
  numberPrefix: string;
  answers: Record<string, string>;
  setAnswers: React.Dispatch<React.SetStateAction<Record<string, string>>>;
}

function QuestionGroup({
  title,
  subtitle,
  accent,
  softBg,
  borderColor,
  questions,
  startIndex,
  numberPrefix,
  answers,
  setAnswers,
}: QuestionGroupProps) {
  return (
    <div style={{ marginBottom: 24 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 10,
            color: accent,
            letterSpacing: '.1em',
            textTransform: 'uppercase',
          }}
        >
          {title}
        </span>
        {subtitle && (
          <span style={{ fontSize: 12, color: 'var(--fg-muted)' }}>— {subtitle}</span>
        )}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {questions.map((q, idx) => {
          const answerKey = numberPrefix === 'P1' ? `p1_${idx}` : `question_${idx}`;
          const value = answers[answerKey] || '';
          const filled = Boolean(value.trim());
          const hasAssumption = value.includes('[SYSTEM ASSUMPTION]');
          const headline = q.blocker || q.question_text || q.question || 'Question';
          const detail = q.blocker
            ? q.question_text || q.question
            : q.why_critical || q.why_it_matters;
          return (
            <div
              key={q.question_id || `${numberPrefix}-${idx}`}
              style={{
                border: `1px solid ${borderColor}`,
                borderRadius: 10,
                background: softBg,
                overflow: 'hidden',
              }}
            >
              <div style={{ padding: '12px 14px 8px', display: 'flex', gap: 8, alignItems: 'flex-start' }}>
                <span
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: 9,
                    letterSpacing: '.08em',
                    padding: '3px 7px',
                    borderRadius: 5,
                    background: 'var(--surface-2)',
                    color: accent,
                    border: `1px solid ${borderColor}`,
                    flexShrink: 0,
                    whiteSpace: 'nowrap',
                  }}
                >
                  {numberPrefix}-{startIndex + idx}
                </span>
                <div style={{ flex: 1 }}>
                  <p
                    style={{
                      fontSize: 13,
                      fontWeight: q.blocker ? 600 : 500,
                      color: 'var(--fg)',
                      marginBottom: detail ? 4 : 0,
                      lineHeight: 1.4,
                    }}
                  >
                    {headline}
                  </p>
                  {detail && (
                    <p style={{ fontSize: 12, color: 'var(--fg-dim)', lineHeight: 1.5 }}>{detail}</p>
                  )}
                  <div style={{ display: 'flex', gap: 5, marginTop: 6, flexWrap: 'wrap' }}>
                    {q.category && (
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
                        {q.category}
                      </span>
                    )}
                    {hasAssumption && (
                      <span
                        style={{
                          fontFamily: 'var(--font-mono)',
                          fontSize: 9,
                          letterSpacing: '.08em',
                          padding: '3px 7px',
                          borderRadius: 5,
                          background: 'rgba(255,194,87,.1)',
                          color: 'var(--warn)',
                          border: '1px solid rgba(255,194,87,.3)',
                          textTransform: 'uppercase',
                        }}
                      >
                        Assumption applied
                      </span>
                    )}
                  </div>
                </div>
              </div>
              <div style={{ padding: '0 14px 12px' }}>
                <textarea
                  value={value}
                  onChange={(e) =>
                    setAnswers((p) => ({ ...p, [answerKey]: e.target.value }))
                  }
                  placeholder="Provide your answer here…"
                  rows={2}
                  style={{
                    width: '100%',
                    background: 'var(--surface-2)',
                    border: `1px solid ${
                      filled ? 'rgba(122,229,130,.3)' : 'var(--border)'
                    }`,
                    borderRadius: 7,
                    padding: '9px 11px',
                    color: 'var(--fg)',
                    fontSize: 13,
                    fontFamily: 'var(--font-sans)',
                    resize: 'vertical',
                    outline: 'none',
                    transition: 'border-color .2s',
                  }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function BackBtn({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        padding: '9px 16px',
        borderRadius: 9,
        background: 'transparent',
        border: '1px solid var(--border-strong)',
        color: 'var(--fg-dim)',
        fontFamily: 'var(--font-sans)',
        fontSize: 13,
        cursor: 'pointer',
      }}
    >
      ← Back
    </button>
  );
}

function PrimaryBtn({
  onClick,
  disabled,
  children,
}: {
  onClick: () => void;
  disabled?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      style={{
        padding: '9px 18px',
        borderRadius: 9,
        background: disabled ? 'var(--surface-2)' : 'var(--accent)',
        color: disabled ? 'var(--fg-muted)' : '#1a0a04',
        border: 'none',
        fontFamily: 'var(--font-display)',
        fontSize: 13,
        fontWeight: 500,
        cursor: disabled ? 'not-allowed' : 'pointer',
      }}
    >
      {children}
    </button>
  );
}
