export interface KpiBlock {
  total_projects: number;
  presales_count: number;
  full_report_count: number;
  avg_readiness: number;
  readiness_trend_7d: number;
}

export interface QuestionsSummary {
  p1_total: number;
  p1_answered: number;
  kickstart_total: number;
  kickstart_answered: number;
  vague_count: number;
}

export interface PendingChangesSummary {
  total: number;
  has_conflicts: boolean;
}

export type ReadinessStatus =
  | 'not_analyzed'
  | 'needs_more_info'
  | 'ready_with_assumptions'
  | 'ready';

export type PipelineStatus =
  | 'idle'
  | 'queued'
  | 'running'
  | 'completed'
  | 'failed'
  | 'cancelled';

export interface ProjectRow {
  chat_history_id: string;
  document_id: string | null;
  title: string;
  analysis_mode: 'presales' | 'full';
  presales_id: string | null;
  full_report_generated: boolean;
  created_at: string | null;
  modified_at: string | null;
  readiness: { score: number; status: ReadinessStatus };
  questions_summary: QuestionsSummary;
  pending_changes: PendingChangesSummary;
  report_versions: number;
  last_message_preview: string;
  pipeline_status: PipelineStatus;
}

export interface InboxQuestion {
  question_id: string;
  chat_history_id: string;
  project_title: string;
  presales_id: string | null;
  question_number: string;
  question_type: 'p1_blocker' | 'kickstart';
  title: string | null;
  question_text: string;
  status: 'pending' | 'needs_review';
  area_or_category: string | null;
}

export interface SubscriptionBlock {
  tier: 'free' | 'basic' | 'plus' | 'pro';
  status: 'active' | 'past_due' | 'canceled';
  period_end: string | null;
  usage: { chats: number; report_regenerations_used: number };
  limits: {
    max_chats: number | null;
    messages_per_chat: number | null;
    monthly_report_regen: number | null;
  };
}

export interface OverviewResponse {
  kpis: KpiBlock;
  projects: ProjectRow[];
  questions_inbox: InboxQuestion[];
  subscription: SubscriptionBlock | null;
}
