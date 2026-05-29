import { useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { toast } from 'react-hot-toast';
import { isAxiosError } from 'axios';
import PipelineProgress from '../components/pipeline/PipelineProgress';
import {
  startFullPipeline,
  resumeFullPipeline,
  getFullPipelineStatus,
  type PipelineRunSnapshot,
} from '../services/fullPipelineService';

const POLL_INTERVAL_MS = 2000;

// Map LangGraph node names (what the backend stores in last_completed_node)
// to human-readable labels for the resume banner. Mirrors NODE_TO_STAGE in
// src/agents/pipeline_runner.py.
const NODE_LABELS: Record<string, string> = {
  req_analyse_node:            'Analyzing requirements',
  amb_resolve_node:            'Resolving ambiguities',
  validator_node:              'Validating consistency',
  solution_architectures_node: 'Designing solution architecture',
  critic_node:                 'Critic review',
  evidence_gather_node:        'Gathering evidence',
  feasibility_estimator_node:  'Estimating feasibility',
  ba_final_report_node:        'Generating final report',
};

/**
 * Live progress page for the 9-agent pipeline.
 *
 * Polls /full-pipeline/status every 2s. On `idle` it auto-starts the pipeline
 * (covers a user landing here directly via project card). On `completed` it
 * navigates to /chat/:id. On `failed` it surfaces the error with a Retry.
 */
export default function FullPipelineProgress() {
  const { chatHistoryId } = useParams<{ chatHistoryId: string }>();
  const navigate = useNavigate();

  const [snapshot, setSnapshot] = useState<PipelineRunSnapshot | null>(null);
  const [hasStarted, setHasStarted] = useState(false);
  const [actionInFlight, setActionInFlight] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Polling loop
  useEffect(() => {
    if (!chatHistoryId) return;

    let cancelled = false;
    const tick = async () => {
      try {
        const snap = await getFullPipelineStatus(chatHistoryId);
        if (cancelled) return;
        setSnapshot(snap);

        // Auto-start once if no run exists yet.
        if (snap.status === 'idle' && !hasStarted) {
          setHasStarted(true);
          try {
            await startFullPipeline(chatHistoryId);
          } catch (err) {
            const detail =
              (isAxiosError(err) && (err.response?.data as { detail?: string })?.detail) ||
              (err instanceof Error ? err.message : 'Failed to start pipeline.');
            toast.error(detail);
          }
        }

        if (snap.status === 'completed') {
          if (intervalRef.current) clearInterval(intervalRef.current);
          navigate(`/chat/${chatHistoryId}`, { replace: true });
        }
      } catch (err) {
        if (cancelled) return;
        // Non-fatal: keep polling. Network blip should not kill the UI.
        console.error('pipeline status poll failed', err);
      }
    };

    void tick();
    intervalRef.current = setInterval(() => void tick(), POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [chatHistoryId, hasStarted, navigate]);

  const handleRetry = async () => {
    if (!chatHistoryId || actionInFlight) return;
    setActionInFlight(true);
    try {
      await startFullPipeline(chatHistoryId);
      // Full restart wipes prior progress on the server; mirror that locally.
      setSnapshot((s) =>
        s
          ? {
              ...s,
              status: 'queued',
              error: null,
              stages_completed: [],
              current_stage: null,
              loop_count: 0,
              last_completed_node: null,
              resumed_from: null,
            }
          : s,
      );
      toast.success('Pipeline restarted.');
    } catch (err) {
      const detail =
        (isAxiosError(err) && (err.response?.data as { detail?: string })?.detail) ||
        (err instanceof Error ? err.message : 'Failed to restart pipeline.');
      toast.error(detail);
    } finally {
      setActionInFlight(false);
    }
  };

  const handleResume = async () => {
    if (!chatHistoryId || actionInFlight) return;
    setActionInFlight(true);
    try {
      const data = await resumeFullPipeline(chatHistoryId);
      // Preserve the prior snapshot's stages_completed so the UI doesn't blank
      // out between the click and the next poll. Only flip status/error and
      // attach the resume marker.
      setSnapshot((s) =>
        s
          ? {
              ...s,
              status: 'queued',
              error: null,
              resumed_from: data.resumed_from ?? s.last_completed_node ?? null,
              last_completed_node: data.last_completed_node ?? s.last_completed_node ?? null,
              // Prefer the server-side list if it came back; otherwise keep ours.
              stages_completed:
                data.stages_completed && data.stages_completed.length > 0
                  ? data.stages_completed
                  : s.stages_completed,
              current_stage: data.current_stage ?? s.current_stage,
            }
          : s,
      );
      toast.success('Pipeline resumed from last checkpoint.');
    } catch (err) {
      // 409 = no resumable snapshot; fall back to a clean retry to keep the user unblocked.
      const status = isAxiosError(err) ? err.response?.status : undefined;
      if (status === 409) {
        toast('No checkpoint available — starting a fresh run.');
        setActionInFlight(false);
        await handleRetry();
        return;
      }
      const detail =
        (isAxiosError(err) && (err.response?.data as { detail?: string })?.detail) ||
        (err instanceof Error ? err.message : 'Failed to resume pipeline.');
      toast.error(detail);
    } finally {
      setActionInFlight(false);
    }
  };

  if (!chatHistoryId) {
    return null;
  }

  const isFailed = snapshot?.status === 'failed';
  const canResume = isFailed && Boolean(snapshot?.last_completed_node);
  const showResumeBanner =
    !!snapshot &&
    !!snapshot.resumed_from &&
    (snapshot.status === 'queued' || snapshot.status === 'running');
  const resumeLabel = snapshot?.resumed_from
    ? NODE_LABELS[snapshot.resumed_from] ?? snapshot.resumed_from
    : null;
  const completedCount = snapshot?.stages_completed?.length ?? 0;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      <div
        style={{
          flexShrink: 0,
          height: 52,
          borderBottom: '1px solid var(--border)',
          display: 'flex',
          alignItems: 'center',
          padding: '0 28px',
          background: 'var(--surface)',
          gap: 16,
        }}
      >
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 10,
            color: 'var(--fg-muted)',
            letterSpacing: '.1em',
            textTransform: 'uppercase',
          }}
        >
          Generating full report
        </span>
        <div style={{ flex: 1 }} />
        <button
          type="button"
          onClick={() => navigate('/projects')}
          style={{
            padding: '6px 12px',
            background: 'transparent',
            border: '1px solid var(--border-strong)',
            borderRadius: 8,
            color: 'var(--fg-dim)',
            fontSize: 12,
            cursor: 'pointer',
            fontFamily: 'var(--font-sans)',
          }}
        >
          ← Projects
        </button>
      </div>

      <div style={{ flex: 1, overflowY: 'auto' }}>
        <div style={{ maxWidth: 720, margin: '0 auto', padding: '32px 24px 8px' }}>
          <h1
            style={{
              fontFamily: 'var(--font-display)',
              fontSize: 22,
              fontWeight: 400,
              letterSpacing: '-.02em',
              color: 'var(--fg)',
              margin: 0,
              marginBottom: 6,
            }}
          >
            Running the full alignment pipeline
          </h1>
          <p style={{ fontSize: 13, color: 'var(--fg-muted)', margin: 0 }}>
            This typically takes 10–15 minutes. You can leave this page — the run will keep
            going and you can return to it from Projects.
          </p>
        </div>

        {showResumeBanner && (
          <div style={{ maxWidth: 720, margin: '0 auto', padding: '16px 24px 0' }}>
            <div
              style={{
                padding: '10px 14px',
                borderRadius: 10,
                border: '1px solid rgba(255,138,101,.25)',
                background: 'var(--accent-soft)',
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                fontSize: 12,
                color: 'var(--accent)',
                fontFamily: 'var(--font-sans)',
              }}
            >
              <span
                style={{
                  width: 10,
                  height: 10,
                  borderRadius: '50%',
                  border: '2px solid rgba(255,138,101,.3)',
                  borderTopColor: 'var(--accent)',
                  animation: 'spin 1s linear infinite',
                  display: 'inline-block',
                  flexShrink: 0,
                }}
              />
              <span>
                Resuming from <strong>{resumeLabel}</strong>
                {completedCount > 0 && ` · ${completedCount} stage${completedCount === 1 ? '' : 's'} already complete`}
              </span>
            </div>
          </div>
        )}

        {snapshot && <PipelineProgress snapshot={snapshot} />}

        {isFailed && (
          <div style={{ maxWidth: 720, margin: '0 auto', padding: '12px 24px 32px' }}>
            <div
              style={{
                padding: 16,
                borderRadius: 10,
                border: '1px solid rgba(255,106,106,.25)',
                background: 'rgba(255,106,106,.06)',
              }}
            >
              <p
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: 10,
                  color: 'var(--danger)',
                  letterSpacing: '.1em',
                  textTransform: 'uppercase',
                  margin: 0,
                  marginBottom: 6,
                }}
              >
                Pipeline failed
              </p>
              <p style={{ fontSize: 13, color: 'var(--fg)', margin: 0, marginBottom: 12 }}>
                {snapshot?.error || 'Unknown error.'}
              </p>
              <div style={{ display: 'flex', gap: 8 }}>
                <button
                  type="button"
                  disabled={actionInFlight}
                  onClick={canResume ? handleResume : handleRetry}
                  style={{
                    padding: '8px 14px',
                    background: 'var(--accent)',
                    color: '#1a0a04',
                    border: 'none',
                    borderRadius: 8,
                    fontSize: 13,
                    fontWeight: 500,
                    cursor: actionInFlight ? 'wait' : 'pointer',
                    opacity: actionInFlight ? 0.6 : 1,
                    fontFamily: 'var(--font-sans)',
                  }}
                  title={
                    canResume
                      ? `Resume from ${
                          (snapshot?.last_completed_node &&
                            NODE_LABELS[snapshot.last_completed_node]) ||
                          snapshot?.last_completed_node ||
                          'last checkpoint'
                        }`
                      : undefined
                  }
                >
                  {actionInFlight ? 'Working…' : canResume ? 'Resume' : 'Retry'}
                </button>
                {canResume && (
                  <button
                    type="button"
                    disabled={actionInFlight}
                    onClick={handleRetry}
                    style={{
                      padding: '8px 14px',
                      background: 'transparent',
                      color: 'var(--fg-dim)',
                      border: '1px solid var(--border-strong)',
                      borderRadius: 8,
                      fontSize: 13,
                      cursor: actionInFlight ? 'wait' : 'pointer',
                      opacity: actionInFlight ? 0.6 : 1,
                      fontFamily: 'var(--font-sans)',
                    }}
                  >
                    Start fresh
                  </button>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
