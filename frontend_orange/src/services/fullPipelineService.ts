import api from './api';

export type PipelineStatus =
  | 'idle'
  | 'queued'
  | 'running'
  | 'completed'
  | 'failed'
  | 'cancelled';

export interface PipelineStageEntry {
  stage: string;
  completed_at: string;
  duration_ms: number;
}

export interface PipelineRunSnapshot {
  run_id?: string;
  chat_history_id: string;
  status: PipelineStatus;
  current_stage: string | null;
  stages_completed: PipelineStageEntry[];
  loop_count: number;
  error: string | null;
  started_at?: string | null;
  completed_at?: string | null;
}

/** Kick off the 9-agent pipeline. Returns 202 immediately. */
export async function startFullPipeline(chatHistoryId: string) {
  const form = new FormData();
  form.append('chat_history_id', chatHistoryId);
  const { data } = await api.post('/full-pipeline/start', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return data as {
    run_id: string;
    chat_history_id: string;
    status: PipelineStatus;
    current_stage: string | null;
    message?: string;
  };
}

/** Poll the current run state. Returns { status: 'idle' } if no run exists. */
export async function getFullPipelineStatus(
  chatHistoryId: string,
): Promise<PipelineRunSnapshot> {
  const { data } = await api.get(`/full-pipeline/status/${chatHistoryId}`);
  // Backend returns { status: 'idle', chat_history_id } when no run exists;
  // normalize to the full snapshot shape so consumers can rely on the fields.
  return {
    chat_history_id: chatHistoryId,
    status: 'idle',
    current_stage: null,
    stages_completed: [],
    loop_count: 0,
    error: null,
    ...data,
  } as PipelineRunSnapshot;
}
