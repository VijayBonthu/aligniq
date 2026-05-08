import { useEffect, useState } from 'react';
import { toast } from 'react-hot-toast';
import * as presalesService from '../../services/presalesService';

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
  onGenerateReport: (assumptions: AnalysisAssumption[]) => void;
}

interface AnalysisData {
  readiness?: {
    score?: number;
    status?: string;
    summary?: string;
  };
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

export default function AnalysisStep({
  presalesId,
  generating,
  onBack,
  onApplyAssumptions,
  onGenerateReport,
}: AnalysisStepProps) {
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<AnalysisData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await presalesService.analyze(presalesId);
        if (!cancelled) setData(res as AnalysisData);
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

  if (loading) {
    return (
      <div style={{ maxWidth: 720, margin: '0 auto', padding: '80px 24px', textAlign: 'center' }}>
        <div
          style={{
            width: 36,
            height: 36,
            margin: '0 auto 18px',
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
          STEP 3 OF 4
        </p>
        <p style={{ fontSize: 14, color: 'var(--fg-dim)' }}>
          Cross-checking your answers, hunting for contradictions, scoring readiness…
        </p>
      </div>
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

  const score = data.readiness?.score ?? 0;
  const statusKey = data.readiness?.status || 'not_analyzed';
  const status = STATUS_LABELS[statusKey] || STATUS_LABELS.not_analyzed;
  const summary = data.readiness?.summary || '';
  const contradictions = data.contradictions || [];
  const vague = data.vague_answers || [];
  const assumptions = data.assumptions || [];
  const recommendations = data.recommendations || [];

  if (generating) {
    return (
      <div style={{ maxWidth: 720, margin: '0 auto', padding: '80px 24px', textAlign: 'center' }}>
        <div
          style={{
            width: 36,
            height: 36,
            margin: '0 auto 18px',
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
          STEP 4 OF 4
        </p>
        <p style={{ fontSize: 14, color: 'var(--fg-dim)' }}>
          Generating the full alignment report — this can take a minute or two…
        </p>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 720, margin: '0 auto', padding: '40px 24px' }}>
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
          fontSize: 26,
          fontWeight: 400,
          letterSpacing: '-.02em',
          color: 'var(--fg)',
          marginBottom: 6,
        }}
      >
        Readiness analysis
      </h1>
      <p style={{ fontSize: 13, color: 'var(--fg-muted)', marginBottom: 28 }}>
        AlignIQ has analysed your answers. Apply assumptions for blanks, edit if needed, or generate the final report.
      </p>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'auto 1fr',
          gap: 28,
          padding: 24,
          background: 'var(--surface)',
          border: '1px solid var(--border)',
          borderRadius: 14,
          marginBottom: 20,
          alignItems: 'center',
        }}
      >
        <ReadinessRing score={score} />
        <div>
          <p
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 10,
              color: status.color,
              letterSpacing: '.1em',
              textTransform: 'uppercase',
              marginBottom: 6,
            }}
          >
            {status.label}
          </p>
          {summary && (
            <p style={{ fontSize: 14, color: 'var(--fg)', lineHeight: 1.6, marginBottom: 12 }}>
              {summary}
            </p>
          )}
          <div style={{ display: 'flex', gap: 18 }}>
            <Stat val={contradictions.length} label="Contradictions" color="var(--danger)" />
            <Stat val={vague.length} label="Vague answers" color="var(--warn)" />
            <Stat val={assumptions.length} label="Assumptions" color="var(--ok)" />
          </div>
        </div>
      </div>

      {contradictions.length > 0 && (
        <IssueGroup
          title="Contradictions"
          accent="var(--danger)"
          items={contradictions.map((c) => ({
            heading: c.question_text || c.description || 'Contradiction',
            body: c.issue || c.description,
            suggestion: c.suggestion || c.suggested_resolution,
          }))}
        />
      )}
      {vague.length > 0 && (
        <IssueGroup
          title="Vague answers"
          accent="var(--warn)"
          items={vague.map((v) => ({
            heading: v.question_text || 'Vague answer',
            body: v.issue,
            suggestion: v.suggestion || v.expected_format,
          }))}
        />
      )}
      {assumptions.length > 0 && (
        <IssueGroup
          title={`Suggested assumptions · ${assumptions.length}`}
          accent="var(--ok)"
          items={assumptions.map((a) => ({
            heading: a.assumption || a.text || 'Assumption',
            body: a.basis,
            suggestion: a.impact_if_wrong,
            badge: a.impact || a.risk_level,
          }))}
        />
      )}

      {recommendations.length > 0 && (
        <div
          style={{
            marginBottom: 24,
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
                marginBottom: 8,
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

      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          justifyContent: 'space-between',
          alignItems: 'center',
          gap: 10,
          marginTop: 24,
        }}
      >
        <BackBtn onClick={onBack} />
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          {assumptions.length > 0 && (
            <button
              type="button"
              onClick={() => onApplyAssumptions(assumptions)}
              style={{
                padding: '10px 16px',
                borderRadius: 9,
                background: 'var(--surface-2)',
                color: 'var(--fg)',
                border: '1px solid var(--border-strong)',
                fontFamily: 'var(--font-sans)',
                fontSize: 13,
                fontWeight: 500,
                cursor: 'pointer',
              }}
            >
              Apply {assumptions.length} assumption{assumptions.length === 1 ? '' : 's'} → edit
            </button>
          )}
          <button
            type="button"
            onClick={() => onGenerateReport(assumptions)}
            style={{
              minWidth: 220,
              padding: '11px 20px',
              borderRadius: 10,
              border: 'none',
              background: 'var(--accent)',
              color: '#1a0a04',
              fontFamily: 'var(--font-display)',
              fontSize: 14,
              fontWeight: 500,
              cursor: 'pointer',
            }}
          >
            Generate full report →
          </button>
        </div>
      </div>
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

function Stat({ val, label, color }: { val: number; label: string; color: string }) {
  return (
    <div style={{ textAlign: 'center' }}>
      <p style={{ fontFamily: 'var(--font-display)', fontSize: 22, color, lineHeight: 1 }}>{val}</p>
      <p
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 9,
          color: 'var(--fg-muted)',
          textTransform: 'uppercase',
          letterSpacing: '.06em',
          marginTop: 2,
        }}
      >
        {label}
      </p>
    </div>
  );
}

interface IssueItem {
  heading: string;
  body?: string;
  suggestion?: string;
  badge?: string;
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
        borderRadius: 10,
        overflow: 'hidden',
      }}
    >
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        style={{
          width: '100%',
          padding: '11px 14px',
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
                padding: '10px 14px',
                borderTop: i > 0 ? '1px solid var(--border)' : 'none',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                <p style={{ fontSize: 13, color: 'var(--fg)', fontWeight: 500, flex: 1 }}>
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
                <p style={{ fontSize: 12.5, color: 'var(--fg-dim)', lineHeight: 1.5 }}>
                  {it.body}
                </p>
              )}
              {it.suggestion && (
                <p
                  style={{
                    marginTop: 6,
                    padding: '6px 10px',
                    background: 'var(--surface-2)',
                    borderRadius: 6,
                    fontSize: 12,
                    color: 'var(--fg-dim)',
                    lineHeight: 1.5,
                  }}
                >
                  <span style={{ color: 'var(--accent)' }}>→ </span>
                  {it.suggestion}
                </p>
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
      ← Back to questions
    </button>
  );
}
