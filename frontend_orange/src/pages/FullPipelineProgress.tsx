import { useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { toast } from 'react-hot-toast';
import { isAxiosError } from 'axios';
import PipelineProgress from '../components/pipeline/PipelineProgress';
import {
  startFullPipeline,
  getFullPipelineStatus,
  type PipelineRunSnapshot,
} from '../services/fullPipelineService';

const POLL_INTERVAL_MS = 2000;

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
    if (!chatHistoryId) return;
    try {
      await startFullPipeline(chatHistoryId);
      setSnapshot((s) => (s ? { ...s, status: 'queued', error: null } : s));
      toast.success('Pipeline restarted.');
    } catch (err) {
      const detail =
        (isAxiosError(err) && (err.response?.data as { detail?: string })?.detail) ||
        (err instanceof Error ? err.message : 'Failed to restart pipeline.');
      toast.error(detail);
    }
  };

  if (!chatHistoryId) {
    return null;
  }

  const isFailed = snapshot?.status === 'failed';

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
              <button
                type="button"
                onClick={handleRetry}
                style={{
                  padding: '8px 14px',
                  background: 'var(--accent)',
                  color: '#1a0a04',
                  border: 'none',
                  borderRadius: 8,
                  fontSize: 13,
                  fontWeight: 500,
                  cursor: 'pointer',
                  fontFamily: 'var(--font-sans)',
                }}
              >
                Retry
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
