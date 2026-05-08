import type { CSSProperties } from 'react';
import type { PipelineRunSnapshot } from '../../services/fullPipelineService';

/**
 * Per-stage progress for the 9-agent full pipeline.
 *
 * Visual treatment ported from
 * `design/extracted/aligniq (1)/New Project Flow.html` (ProcessingSteps block).
 * Each row is one of three states: pending / active (RUNNING) / done (DONE).
 *
 * Stage order MUST match `STAGE_ORDER` in `src/agents/pipeline_runner.py`.
 */

type StageId =
  | 'requirements_analyzer'
  | 'ambiguity_resolver'
  | 'validator_agent'
  | 'solution_architectures'
  | 'critic_agent'
  | 'evidence_gather_agent'
  | 'feasibility_estimator'
  | 'ba_final_report_generation';

interface StageDef {
  id: StageId;
  label: string;
  icon: string;
}

const STAGES: StageDef[] = [
  { id: 'requirements_analyzer',       label: 'Analyzing requirements',       icon: '📋' },
  { id: 'ambiguity_resolver',          label: 'Resolving ambiguities',         icon: '🔍' },
  { id: 'validator_agent',             label: 'Validating consistency',        icon: '✓' },
  { id: 'solution_architectures',      label: 'Designing solution architecture', icon: '🧠' },
  { id: 'critic_agent',                label: 'Critic review',                  icon: '⚖' },
  { id: 'evidence_gather_agent',       label: 'Gathering evidence',             icon: '🔎' },
  { id: 'feasibility_estimator',       label: 'Estimating feasibility',         icon: '⏱' },
  { id: 'ba_final_report_generation',  label: 'Generating final report',        icon: '📄' },
];

interface Props {
  snapshot: PipelineRunSnapshot;
}

export default function PipelineProgress({ snapshot }: Props) {
  const completedSet = new Set((snapshot.stages_completed || []).map((s) => s.stage));
  const current = snapshot.current_stage;

  return (
    <div style={{ maxWidth: 720, margin: '0 auto', padding: '32px 24px' }}>
      <p
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 10,
          letterSpacing: '.1em',
          textTransform: 'uppercase',
          color: 'var(--accent)',
          margin: 0,
          marginBottom: 18,
        }}
      >
        9-AGENT PIPELINE RUNNING
      </p>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {STAGES.map((stage) => {
          const isDone = completedSet.has(stage.id);
          const isActive = !isDone && stage.id === current;
          const showLoop = stage.id === 'critic_agent' && (snapshot.loop_count || 0) > 0;
          return (
            <StageRow
              key={stage.id}
              stage={stage}
              state={isDone ? 'done' : isActive ? 'active' : 'pending'}
              loopBadge={showLoop ? `loop ${snapshot.loop_count}/3` : null}
            />
          );
        })}
      </div>
    </div>
  );
}

function StageRow({
  stage,
  state,
  loopBadge,
}: {
  stage: StageDef;
  state: 'pending' | 'active' | 'done';
  loopBadge: string | null;
}) {
  const rowStyle: CSSProperties = {
    display: 'flex',
    alignItems: 'center',
    gap: 12,
    padding: '12px 14px',
    borderRadius: 10,
    border:
      state === 'active'
        ? '1px solid rgba(255,138,101,.3)'
        : state === 'done'
        ? '1px solid var(--border)'
        : '1px solid transparent',
    background:
      state === 'active'
        ? 'var(--accent-soft)'
        : state === 'done'
        ? 'var(--surface-2)'
        : 'transparent',
    transition: 'background .2s ease, border-color .2s ease',
  };
  const iconCircle: CSSProperties = {
    width: 28,
    height: 28,
    borderRadius: '50%',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
    fontSize: 13,
    border:
      state === 'done'
        ? '1px solid rgba(122,229,130,.3)'
        : state === 'active'
        ? '1px solid rgba(255,138,101,.3)'
        : '1px solid var(--border)',
    background:
      state === 'done'
        ? 'var(--ok-soft)'
        : state === 'active'
        ? 'var(--accent-soft)'
        : 'var(--surface)',
  };
  const labelStyle: CSSProperties = {
    flex: 1,
    fontSize: 13,
    fontFamily: 'var(--font-sans)',
    fontWeight: state === 'active' ? 500 : 400,
    color:
      state === 'active'
        ? 'var(--accent)'
        : state === 'done'
        ? 'var(--fg)'
        : 'var(--fg-muted)',
  };
  const badgeBase: CSSProperties = {
    fontFamily: 'var(--font-mono)',
    fontSize: 9,
    letterSpacing: '.06em',
    textTransform: 'uppercase',
    flexShrink: 0,
  };

  return (
    <div style={rowStyle}>
      <div style={iconCircle}>
        {state === 'done' ? (
          <svg width="14" height="14" fill="none" stroke="var(--ok)" viewBox="0 0 24 24">
            <path d="M5 13l4 4L19 7" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        ) : state === 'active' ? (
          <span
            style={{
              width: 12,
              height: 12,
              borderRadius: '50%',
              border: '2px solid rgba(255,138,101,.3)',
              borderTopColor: 'var(--accent)',
              animation: 'spin 1s linear infinite',
              display: 'inline-block',
            }}
          />
        ) : (
          <span style={{ opacity: 0.7 }}>{stage.icon}</span>
        )}
      </div>
      <div style={labelStyle}>{stage.label}</div>
      {loopBadge && (
        <span style={{ ...badgeBase, color: 'var(--warn)' }}>{loopBadge}</span>
      )}
      {state === 'active' && (
        <span
          style={{
            ...badgeBase,
            color: 'var(--accent)',
            animation: 'pulse 2s ease-in-out infinite',
          }}
        >
          RUNNING
        </span>
      )}
      {state === 'done' && (
        <span style={{ ...badgeBase, color: 'var(--ok)' }}>DONE</span>
      )}
    </div>
  );
}
