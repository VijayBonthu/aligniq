import { useEffect, useMemo, useState } from 'react';
import { toast } from 'react-hot-toast';
import * as presalesService from '../../services/presalesService';
import { ThemeSectionHeader } from '../ui/QuestionMeta';

export interface AnalysisAssumption {
  id?: string;
  for_question_id?: string;
  text?: string;
  assumption?: string;
  impact?: string;
  risk_level?: string;
  basis?: string;
  impact_if_wrong?: string;
}

interface AnalysisStepProps {
  presalesId: string;
  generating: boolean;
  onBack: () => void;
  onApplyAssumptions: (assumptions: AnalysisAssumption[]) => void;
  onGenerateReport: (assumptions: AnalysisAssumption[], readinessStatus?: string) => void;
  /** Lifts the analysis result to the flow so the Questions step can render
   *  inline assumption previews under unanswered questions. */
  onData?: (data: AnalysisData) => void;
  /** Jump back to the Questions step focused on one question ("Q3" / "P1-2" / "F1"). */
  onReviseAnswer?: (displayId?: string) => void;
}

export interface ReadinessTheme {
  theme?: string;
  answered?: number;
  total?: number;
  status?: string;
}

export interface AnalysisData {
  readiness?: {
    score?: number;
    status?: string;
    summary?: string;
    themes?: ReadinessTheme[];
    top_gaps?: string[];
  };
  created_followups?: Array<{
    question_id?: string;
    question_number?: string;
    question_text?: string;
  }>;
  /** Refreshed question list (includes any newly created follow-ups). */
  questions?: unknown[];
  contradictions?: Array<{
    question_text?: string;
    description?: string;
    issue?: string;
    suggestion?: string;
    suggested_resolution?: string;
    severity?: string;
  }>;
  vague_answers?: Array<{
    question_id?: string;
    question_text?: string;
    issue?: string;
    suggestion?: string;
    expected_format?: string;
  }>;
  assumptions?: AnalysisAssumption[];
  recommendations?: string[];
}

const STATUS_LABELS: Record<string, { label: string; color: string }> = {
  ready: { label: 'Ready', color: 'var(--ok)' },
  ready_with_assumptions: { label: 'Ready with assumptions', color: 'var(--warn)' },
  needs_more_info: { label: 'Needs more info', color: 'var(--danger)' },
  not_analyzed: { label: 'Not analyzed', color: 'var(--fg-muted)' },
};

const RISK_COLOR = (level?: string): string => {
  const l = (level || '').toLowerCase();
  if (l.includes('high')) return 'var(--danger)';
  if (l.includes('med')) return 'var(--warn)';
  if (l.includes('low')) return 'var(--ok)';
  return 'var(--fg-muted)';
};

const keyFor = (i: number) => `a_${i}`;

interface ReviewState {
  included: boolean;
  text: string;
}

export default function AnalysisStep({
  presalesId,
  generating,
  onBack,
  onApplyAssumptions,
  onGenerateReport,
  onData,
  onReviseAnswer,
}: AnalysisStepProps) {
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<AnalysisData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [review, setReview] = useState<Record<string, ReviewState>>({});
  const [editing, setEditing] = useState<Record<string, boolean>>({});

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await presalesService.analyze(presalesId);
        if (!cancelled) {
          setData(res as AnalysisData);
          onData?.(res as AnalysisData);
        }
      } catch (err) {
        console.error('Analyze failed', err);
        if (!cancelled) {
          setError('Failed to run readiness analysis.');
          toast.error('Failed to run readiness analysis.');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [presalesId]);

  // Seed the per-assumption review state once analysis arrives. Default each to
  // "included" (the system inferred them to fill a gap) but fully editable /
  // dismissible — LLM assists, human decides.
  useEffect(() => {
    if (!data?.assumptions) return;
    const seeded: Record<string, ReviewState> = {};
    data.assumptions.forEach((a, i) => {
      seeded[keyFor(i)] = { included: true, text: a.assumption || a.text || '' };
    });
    setReview(seeded);
  }, [data]);

  const assumptions = useMemo(() => data?.assumptions || [], [data]);

  // The curated set: only included assumptions, with any inline edits applied.
  const curated = useMemo(
    () =>
      assumptions
        .map((a, i) => ({ a, k: keyFor(i) }))
        .filter(({ k }) => review[k]?.included)
        .map(({ a, k }) => ({ ...a, assumption: review[k].text, text: review[k].text })),
    [assumptions, review],
  );
  const includedCount = curated.length;

  if (loading) {
    return (
      <ScanningState
        eyebrow="STEP 3 OF 4"
        title="Scoring readiness"
        steps={['Cross-checking your answers', 'Hunting for contradictions', 'Scoring readiness']}
      />
    );
  }

  if (error || !data) {
    return (
      <div style={{ maxWidth: 720, margin: '0 auto', padding: '60px 24px' }}>
        <p style={{ fontSize: 14, color: 'var(--danger)', marginBottom: 24 }}>
          {error || 'Analysis failed.'}
        </p>
        <BackBtn onClick={onBack} />
      </div>
    );
  }

  if (generating) {
    return (
      <ScanningState
        eyebrow="STEP 4 OF 4"
        title="Writing your alignment brief"
        steps={['Folding in your answers', 'Grounding assumptions', 'Composing the brief']}
        note="This can take a minute or two."
      />
    );
  }

  const score = data.readiness?.score ?? 0;
  const statusKey = data.readiness?.status || 'not_analyzed';
  const status = STATUS_LABELS[statusKey] || STATUS_LABELS.not_analyzed;
  const summary = data.readiness?.summary || '';
  const contradictions = data.contradictions || [];
  const vague = data.vague_answers || [];
  const recommendations = data.recommendations || [];

  const setIncluded = (k: string, included: boolean) =>
    setReview((r) => ({ ...r, [k]: { ...r[k], included } }));
  const setText = (k: string, text: string) =>
    setReview((r) => ({ ...r, [k]: { ...r[k], text } }));
  const setAll = (included: boolean) =>
    setReview((r) => {
      const next = { ...r };
      for (const k of Object.keys(next)) next[k] = { ...next[k], included };
      return next;
    });

  return (
    <div style={{ maxWidth: 860, margin: '0 auto', padding: 'clamp(24px, 5vw, 40px) clamp(16px, 4vw, 28px)' }}>
      <header style={{ marginBottom: 24 }}>
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
          STEP 3 OF 4
        </p>
        <h1
          style={{
            fontFamily: 'var(--font-display)',
            fontSize: 'clamp(22px, 5vw, 28px)',
            fontWeight: 400,
            letterSpacing: '-.02em',
            color: 'var(--fg)',
            margin: '0 0 8px',
          }}
        >
          Readiness analysis
        </h1>
        <p style={{ fontSize: 14, color: 'var(--fg-muted)', lineHeight: 1.6, maxWidth: 620, margin: 0 }}>
          We cross-checked your answers and scored how ready this scope is. Review the assumptions we&rsquo;d
          make for any gaps — accept, edit, or drop each one — then generate the brief.
        </p>
      </header>

      {/* Readiness scorecard */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: 'clamp(18px, 4vw, 28px)',
          padding: 'clamp(18px, 4vw, 24px)',
          background: 'var(--surface)',
          border: '1px solid var(--border)',
          borderRadius: 16,
          marginBottom: 18,
          alignItems: 'center',
        }}
      >
        <ReadinessRing score={score} />
        <div style={{ flex: '1 1 240px', minWidth: 0 }}>
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              padding: '4px 10px',
              borderRadius: 999,
              background: `color-mix(in oklab, ${status.color} 12%, transparent)`,
              border: `1px solid color-mix(in oklab, ${status.color} 30%, transparent)`,
              marginBottom: 10,
            }}
          >
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: status.color }} />
            <span
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 10,
                color: status.color,
                letterSpacing: '.08em',
                textTransform: 'uppercase',
              }}
            >
              {status.label}
            </span>
          </span>
          {summary && (
            <p style={{ fontSize: 14, color: 'var(--fg)', lineHeight: 1.6, margin: '0 0 14px' }}>
              {summary}
            </p>
          )}
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            <StatChip val={contradictions.length} label="Contradictions" color="var(--danger)" />
            <StatChip val={vague.length} label="Vague answers" color="var(--warn)" />
            <StatChip val={assumptions.length} label="Assumptions" color="var(--accent)" />
          </div>
        </div>
      </div>

      {((data.readiness?.themes?.length ?? 0) > 0 || (data.readiness?.top_gaps?.length ?? 0) > 0) && (
        <div
          style={{
            padding: '16px 18px',
            borderRadius: 12,
            background: 'var(--surface)',
            border: '1px solid var(--border)',
            marginBottom: 20,
          }}
        >
          <p style={{ fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '.12em',
            textTransform: 'uppercase', color: 'var(--fg-muted)', margin: '0 0 12px' }}>
            What's lacking — readiness by area
          </p>
          {(data.readiness?.themes || []).map((t, i) => (
            <ThemeSectionHeader
              key={t.theme || i}
              theme={t.theme || 'other'}
              answered={t.answered ?? 0}
              total={t.total ?? 0}
              right={
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, textTransform: 'uppercase',
                  color: (t.status === 'weak') ? 'var(--danger)' : (t.status === 'partial') ? 'var(--warn)' : 'var(--ok)' }}>
                  {t.status || ''}
                </span>
              }
            />
          ))}
          {(data.readiness?.top_gaps?.length ?? 0) > 0 && (
            <div style={{ marginTop: 10 }}>
              <p style={{ fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '.1em',
                textTransform: 'uppercase', color: 'var(--danger)', margin: '0 0 6px' }}>
                Biggest gaps
              </p>
              <ul style={{ margin: 0, paddingLeft: 18 }}>
                {(data.readiness?.top_gaps || []).map((g, i) => (
                  <li key={i} style={{ fontSize: 13, color: 'var(--fg-dim)', lineHeight: 1.55, marginBottom: 3 }}>{g}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {statusKey === 'needs_more_info' && (
        <div
          style={{
            display: 'flex',
            gap: 9,
            alignItems: 'flex-start',
            padding: '12px 14px',
            borderRadius: 10,
            background: 'color-mix(in oklab, var(--danger) 7%, transparent)',
            border: '1px solid color-mix(in oklab, var(--danger) 26%, transparent)',
            marginBottom: 20,
          }}
        >
          <svg width="15" height="15" fill="none" stroke="var(--danger)" viewBox="0 0 24 24" style={{ flexShrink: 0, marginTop: 1 }}>
            <circle cx="12" cy="12" r="10" strokeWidth="1.8" />
            <path d="M12 8v4M12 16h.01" strokeWidth="1.8" strokeLinecap="round" />
          </svg>
          <p style={{ fontSize: 12.5, color: 'var(--fg-dim)', lineHeight: 1.5, margin: 0 }}>
            Readiness is low. You can still generate the brief on assumptions, but answering the open
            blockers first will produce a tighter estimate.
          </p>
        </div>
      )}

      {(data.created_followups?.length ?? 0) > 0 && (
        <div
          style={{
            display: 'flex',
            gap: 10,
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            padding: '12px 14px',
            borderRadius: 10,
            background: 'color-mix(in oklab, var(--warn) 7%, transparent)',
            border: '1px solid color-mix(in oklab, var(--warn) 26%, transparent)',
            marginBottom: 16,
          }}
        >
          <div style={{ minWidth: 0 }}>
            <p style={{ fontSize: 13, color: 'var(--fg)', fontWeight: 500, margin: 0 }}>
              {data.created_followups!.length === 1
                ? 'Your answers raised 1 follow-up question'
                : `Your answers raised ${data.created_followups!.length} follow-up questions`}
            </p>
            <p style={{ fontSize: 12, color: 'var(--fg-muted)', margin: '2px 0 0' }}>
              Quick to settle now — each one you answer is one less assumption in the brief.
            </p>
          </div>
          {onReviseAnswer && (
            <button
              type="button"
              onClick={() => onReviseAnswer(data.created_followups?.[0]?.question_number)}
              style={{
                flexShrink: 0,
                padding: '7px 13px',
                borderRadius: 8,
                border: 'none',
                background: 'var(--warn)',
                color: '#1a1a1a',
                fontSize: 12.5,
                fontWeight: 600,
                cursor: 'pointer',
                fontFamily: 'var(--font-sans)',
              }}
            >
              Answer follow-ups →
            </button>
          )}
        </div>
      )}

      {contradictions.length > 0 && (
        <IssueGroup
          title={`Contradictions · ${contradictions.length}`}
          accent="var(--danger)"
          items={contradictions.map((c) => ({
            heading: c.question_text || c.description || 'Contradiction',
            body: c.issue || c.description,
            suggestion: c.suggestion || c.suggested_resolution,
            badge: c.severity,
          }))}
        />
      )}
      {vague.length > 0 && (
        <IssueGroup
          title={`Vague answers · ${vague.length}`}
          accent="var(--warn)"
          items={vague.map((v) => ({
            heading: v.question_text || v.question_id || 'Vague answer',
            body: v.issue,
            suggestion: v.suggestion || v.expected_format,
            action: onReviseAnswer
              ? { label: 'Revise this answer →', onClick: () => onReviseAnswer(v.question_id) }
              : undefined,
          }))}
        />
      )}

      {/* Assumption review — the human-decides surface */}
      {assumptions.length > 0 && (
        <div
          style={{
            marginBottom: 18,
            border: '1px solid var(--border)',
            borderRadius: 14,
            overflow: 'hidden',
          }}
        >
          <div
            style={{
              padding: '14px 16px',
              background: 'var(--bg-2)',
              borderBottom: '1px solid var(--border)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 12,
              flexWrap: 'wrap',
            }}
          >
            <div>
              <p
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: 10,
                  color: 'var(--warn)',
                  letterSpacing: '.1em',
                  textTransform: 'uppercase',
                  margin: 0,
                }}
              >
                ASSUMPTIONS FOR GAPS · {assumptions.length}
              </p>
              <p style={{ fontSize: 12, color: 'var(--fg-muted)', margin: '3px 0 0' }}>
                {includedCount} of {assumptions.length} will be baked into the brief
              </p>
            </div>
            <div style={{ display: 'flex', gap: 6 }}>
              <MiniBtn onClick={() => setAll(true)} active={includedCount === assumptions.length}>
                Accept all
              </MiniBtn>
              <MiniBtn onClick={() => setAll(false)} active={includedCount === 0}>
                Dismiss all
              </MiniBtn>
            </div>
          </div>
          <div>
            {assumptions.map((a, i) => {
              const k = keyFor(i);
              const rs = review[k] || { included: true, text: a.assumption || a.text || '' };
              return (
                <AssumptionCard
                  key={k}
                  index={i}
                  first={i === 0}
                  assumption={a}
                  state={rs}
                  editing={Boolean(editing[k])}
                  onToggle={() => setIncluded(k, !rs.included)}
                  onText={(t) => setText(k, t)}
                  onEdit={() => setEditing((e) => ({ ...e, [k]: !e[k] }))}
                />
              );
            })}
          </div>
        </div>
      )}

      {recommendations.length > 0 && (
        <div
          style={{
            marginBottom: 20,
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
              marginBottom: 10,
            }}
          >
            RECOMMENDATIONS
          </p>
          {recommendations.map((r, i) => (
            <div
              key={i}
              style={{
                display: 'flex',
                gap: 8,
                marginBottom: i === recommendations.length - 1 ? 0 : 8,
                fontSize: 13,
                color: 'var(--fg-dim)',
                lineHeight: 1.5,
              }}
            >
              <span style={{ color: 'var(--accent)', flexShrink: 0, marginTop: 1 }}>→</span>
              {r}
            </div>
          ))}
        </div>
      )}

      {/* Actions */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          justifyContent: 'space-between',
          alignItems: 'center',
          gap: 10,
          marginTop: 22,
        }}
      >
        <BackBtn onClick={onBack} />
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
          {includedCount > 0 && (
            <button
              type="button"
              onClick={() => onApplyAssumptions(curated)}
              style={{
                padding: '11px 16px',
                borderRadius: 10,
                background: 'var(--surface-2)',
                color: 'var(--fg)',
                border: '1px solid var(--border-strong)',
                fontFamily: 'var(--font-sans)',
                fontSize: 13,
                fontWeight: 500,
                cursor: 'pointer',
              }}
            >
              Refine in answers first
            </button>
          )}
          <button
            type="button"
            onClick={() => onGenerateReport(curated, statusKey)}
            style={{
              minWidth: 230,
              padding: '12px 20px',
              borderRadius: 10,
              border: 'none',
              background: 'var(--accent)',
              color: 'var(--accent-ink)',
              fontFamily: 'var(--font-display)',
              fontSize: 14,
              fontWeight: 500,
              cursor: 'pointer',
              boxShadow: 'var(--glow)',
              display: 'inline-flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: 1,
            }}
          >
            <span>Generate brief →</span>
            {assumptions.length > 0 && (
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, opacity: 0.85, fontWeight: 400 }}>
                {includedCount
                  ? `with ${includedCount} assumption${includedCount === 1 ? '' : 's'}`
                  : 'no assumptions applied'}
              </span>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

function ScanningState({
  eyebrow,
  title,
  steps,
  note,
}: {
  eyebrow: string;
  title: string;
  steps: string[];
  note?: string;
}) {
  return (
    <div style={{ maxWidth: 460, margin: '0 auto', padding: '80px 24px', textAlign: 'center' }}>
      <div
        style={{
          width: 38,
          height: 38,
          margin: '0 auto 20px',
          border: '2px solid var(--border-strong)',
          borderTopColor: 'var(--accent)',
          borderRadius: '50%',
          animation: 'spin 1s linear infinite',
        }}
      />
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
        {eyebrow}
      </p>
      <h2
        style={{
          fontFamily: 'var(--font-display)',
          fontSize: 22,
          fontWeight: 400,
          letterSpacing: '-.02em',
          color: 'var(--fg)',
          margin: '0 0 18px',
        }}
      >
        {title}
      </h2>
      <div style={{ display: 'inline-flex', flexDirection: 'column', gap: 9, textAlign: 'left' }}>
        {steps.map((s, i) => (
          <div key={s} style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
            <span
              style={{
                width: 6,
                height: 6,
                borderRadius: '50%',
                background: 'var(--accent)',
                animation: 'pulse 1.6s ease-in-out infinite',
                animationDelay: `${i * 0.25}s`,
              }}
            />
            <span style={{ fontSize: 13, color: 'var(--fg-dim)' }}>{s}</span>
          </div>
        ))}
      </div>
      {note && (
        <p style={{ fontSize: 12, color: 'var(--fg-muted)', marginTop: 18 }}>{note}</p>
      )}
    </div>
  );
}

function ReadinessRing({ score, size = 120 }: { score: number; size?: number }) {
  // Backend returns readiness.score as 0.0–1.0; scale up if it's in that range,
  // otherwise treat it as already-percentage (defensive against future changes).
  const pct = score <= 1 ? score * 100 : score;
  const clamped = Math.max(0, Math.min(100, Math.round(pct)));
  const r = 46;
  const circ = 2 * Math.PI * r;
  const fill = (clamped / 100) * circ;
  const color =
    clamped >= 75 ? 'var(--ok)' : clamped >= 50 ? 'var(--warn)' : 'var(--danger)';

  return (
    <div style={{ position: 'relative', width: size, height: size }}>
      <svg width={size} height={size} viewBox="0 0 100 100">
        <circle cx="50" cy="50" r={r} fill="none" stroke="var(--surface-2)" strokeWidth="5" />
        <circle
          cx="50"
          cy="50"
          r={r}
          fill="none"
          stroke={color}
          strokeWidth="5"
          strokeDasharray={`${fill} ${circ - fill}`}
          strokeDashoffset={circ * 0.25}
          strokeLinecap="round"
          style={{ transition: 'stroke-dasharray .8s cubic-bezier(.4,0,.2,1)' }}
        />
      </svg>
      <div
        style={{
          position: 'absolute',
          inset: 0,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <span
          style={{
            fontFamily: 'var(--font-display)',
            fontSize: 28,
            color,
            lineHeight: 1,
            letterSpacing: '-.02em',
          }}
        >
          {clamped}
        </span>
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 9,
            color: 'var(--fg-muted)',
            letterSpacing: '.08em',
            textTransform: 'uppercase',
          }}
        >
          / 100
        </span>
      </div>
    </div>
  );
}

function StatChip({ val, label, color }: { val: number; label: string; color: string }) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        padding: '7px 12px',
        borderRadius: 9,
        background: 'var(--surface-2)',
        border: '1px solid var(--border)',
      }}
    >
      <span style={{ fontFamily: 'var(--font-display)', fontSize: 20, color, lineHeight: 1 }}>{val}</span>
      <span
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 9,
          color: 'var(--fg-muted)',
          textTransform: 'uppercase',
          letterSpacing: '.06em',
        }}
      >
        {label}
      </span>
    </div>
  );
}

function MiniBtn({
  onClick,
  active,
  children,
}: {
  onClick: () => void;
  active?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        padding: '5px 10px',
        borderRadius: 7,
        border: `1px solid ${active ? 'var(--accent)' : 'var(--border)'}`,
        background: active ? 'var(--accent-soft)' : 'transparent',
        color: active ? 'var(--accent)' : 'var(--fg-dim)',
        fontSize: 11.5,
        fontWeight: 500,
        cursor: 'pointer',
        fontFamily: 'var(--font-sans)',
      }}
    >
      {children}
    </button>
  );
}

function AssumptionCard({
  index,
  first,
  assumption: a,
  state,
  editing,
  onToggle,
  onText,
  onEdit,
}: {
  index: number;
  first: boolean;
  assumption: AnalysisAssumption;
  state: ReviewState;
  editing: boolean;
  onToggle: () => void;
  onText: (t: string) => void;
  onEdit: () => void;
}) {
  const included = state.included;
  const riskColor = RISK_COLOR(a.impact || a.risk_level);
  const riskLabel = a.impact || a.risk_level;

  return (
    <div
      style={{
        padding: '14px 16px',
        borderTop: first ? 'none' : '1px solid var(--border)',
        background: included ? 'transparent' : 'var(--bg-2)',
        opacity: included ? 1 : 0.6,
        transition: 'opacity .15s, background .15s',
      }}
    >
      <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
        {/* Include toggle */}
        <button
          type="button"
          onClick={onToggle}
          aria-label={included ? 'Exclude assumption' : 'Include assumption'}
          style={{
            flexShrink: 0,
            width: 20,
            height: 20,
            marginTop: 1,
            borderRadius: 6,
            border: `1.5px solid ${included ? 'var(--accent)' : 'var(--border-strong)'}`,
            background: included ? 'var(--accent)' : 'transparent',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            cursor: 'pointer',
            transition: 'all .15s',
          }}
        >
          {included && (
            <svg width="12" height="12" fill="none" stroke="var(--accent-ink)" viewBox="0 0 24 24">
              <path d="M5 13l4 4L19 7" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          )}
        </button>

        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
            <span
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 9,
                color: 'var(--fg-muted)',
                letterSpacing: '.06em',
                marginTop: 3,
                flexShrink: 0,
              }}
            >
              A-{index + 1}
            </span>
            {editing ? (
              <textarea
                value={state.text}
                onChange={(e) => onText(e.target.value)}
                rows={2}
                autoFocus
                style={{
                  flex: 1,
                  background: 'var(--surface-2)',
                  border: '1px solid var(--accent)',
                  borderRadius: 7,
                  padding: '8px 10px',
                  color: 'var(--fg)',
                  fontSize: 13.5,
                  fontFamily: 'var(--font-sans)',
                  resize: 'vertical',
                  outline: 'none',
                  lineHeight: 1.5,
                }}
              />
            ) : (
              <p
                style={{
                  flex: 1,
                  fontSize: 13.5,
                  color: 'var(--fg)',
                  fontWeight: 500,
                  lineHeight: 1.5,
                  margin: 0,
                }}
              >
                {state.text || 'Assumption'}
              </p>
            )}
            {riskLabel && (
              <span
                style={{
                  flexShrink: 0,
                  fontFamily: 'var(--font-mono)',
                  fontSize: 9,
                  letterSpacing: '.06em',
                  padding: '3px 7px',
                  borderRadius: 5,
                  background: `color-mix(in oklab, ${riskColor} 12%, transparent)`,
                  color: riskColor,
                  border: `1px solid color-mix(in oklab, ${riskColor} 28%, transparent)`,
                  textTransform: 'uppercase',
                  marginTop: 1,
                }}
              >
                {riskLabel} risk
              </span>
            )}
          </div>

          {a.basis && (
            <p style={{ fontSize: 12, color: 'var(--fg-muted)', lineHeight: 1.5, margin: '7px 0 0', paddingLeft: 26 }}>
              <span style={{ color: 'var(--fg-dim)' }}>Based on: </span>
              {a.basis}
            </p>
          )}
          {a.impact_if_wrong && (
            <p style={{ fontSize: 12, color: 'var(--fg-muted)', lineHeight: 1.5, margin: '4px 0 0', paddingLeft: 26 }}>
              <span style={{ color: riskColor }}>If wrong: </span>
              {a.impact_if_wrong}
            </p>
          )}

          <div style={{ display: 'flex', gap: 14, marginTop: 9, paddingLeft: 26 }}>
            <button
              type="button"
              onClick={onEdit}
              style={{
                background: 'none',
                border: 'none',
                padding: 0,
                color: editing ? 'var(--accent)' : 'var(--fg-dim)',
                fontSize: 12,
                cursor: 'pointer',
                fontFamily: 'var(--font-sans)',
              }}
            >
              {editing ? 'Done' : 'Edit'}
            </button>
            <button
              type="button"
              onClick={onToggle}
              style={{
                background: 'none',
                border: 'none',
                padding: 0,
                color: 'var(--fg-dim)',
                fontSize: 12,
                cursor: 'pointer',
                fontFamily: 'var(--font-sans)',
              }}
            >
              {included ? 'Dismiss' : 'Restore'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

interface IssueItem {
  heading: string;
  body?: string;
  suggestion?: string;
  badge?: string;
  action?: { label: string; onClick: () => void };
}

function IssueGroup({
  title,
  accent,
  items,
}: {
  title: string;
  accent: string;
  items: IssueItem[];
}) {
  const [open, setOpen] = useState(true);
  return (
    <div
      style={{
        marginBottom: 16,
        border: '1px solid var(--border)',
        borderRadius: 12,
        overflow: 'hidden',
      }}
    >
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        style={{
          width: '100%',
          padding: '12px 16px',
          background: 'var(--bg-2)',
          borderBottom: open ? '1px solid var(--border)' : 'none',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          border: 'none',
          cursor: 'pointer',
        }}
      >
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
        <span style={{ fontSize: 12, color: 'var(--fg-muted)' }}>{open ? '▾' : '▸'}</span>
      </button>
      {open && (
        <div>
          {items.map((it, i) => (
            <div
              key={i}
              style={{
                padding: '12px 16px',
                borderTop: i > 0 ? '1px solid var(--border)' : 'none',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                <p style={{ fontSize: 13, color: 'var(--fg)', fontWeight: 500, flex: 1, lineHeight: 1.4 }}>
                  {it.heading}
                </p>
                {it.badge && (
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
                    {it.badge}
                  </span>
                )}
              </div>
              {it.body && (
                <p style={{ fontSize: 12.5, color: 'var(--fg-dim)', lineHeight: 1.5 }}>{it.body}</p>
              )}
              {it.suggestion && (
                <p
                  style={{
                    marginTop: 7,
                    padding: '7px 11px',
                    background: 'var(--surface-2)',
                    borderRadius: 7,
                    fontSize: 12,
                    color: 'var(--fg-dim)',
                    lineHeight: 1.5,
                  }}
                >
                  <span style={{ color: 'var(--accent)' }}>→ </span>
                  {it.suggestion}
                </p>
              )}
              {it.action && (
                <button
                  type="button"
                  onClick={it.action.onClick}
                  style={{
                    marginTop: 8,
                    padding: '5px 10px',
                    borderRadius: 7,
                    border: '1px solid var(--border-strong)',
                    background: 'transparent',
                    color: 'var(--fg)',
                    fontSize: 11.5,
                    fontWeight: 500,
                    cursor: 'pointer',
                    fontFamily: 'var(--font-sans)',
                  }}
                >
                  {it.action.label}
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
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
      }}
    >
      ← Back to questions
    </button>
  );
}
