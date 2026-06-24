export interface Message {
  id?: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  selected?: boolean;
  type?: string;
}

export interface ConversationMetadata {
  chat_history_id: string;
  title: string;
  modified_at: string;
  document_id?: string;
}

export interface GroupedConversations {
  today: ConversationMetadata[];
  yesterday: ConversationMetadata[];
  lastWeek: ConversationMetadata[];
  older: ConversationMetadata[];
}

export interface P1Blocker {
  area: string;
  blocker: string;
  why_it_matters: string;
  question: string;
  answer?: string;
}

export interface KickstartQuestion {
  category: string;
  question: string;
  why_critical: string;
  impact_if_unknown: string;
  answer?: string;
}

export interface ReadinessResult {
  score: number;
  status: 'not_analyzed' | 'needs_more_info' | 'ready_with_assumptions' | 'ready';
  summary?: string;
  p1_answered?: number;
  p1_total?: number;
  kickstart_answered?: number;
  kickstart_total?: number;
}

export interface Assumption {
  for_question_id: string;
  assumption: string;
  basis: string;
  risk_level: 'low' | 'medium' | 'high';
  impact_if_wrong: string;
}

export interface Contradiction {
  question_ids: string[];
  description: string;
  explanation: string;
  suggested_resolution: string;
}

export interface VagueAnswer {
  question_id: string;
  current_answer: string;
  issue: string;
  expected_format: string;
  impact: string;
}

export interface InvalidatedQuestion {
  question_id: string;
  reason: string;
  invalidated_by: string;
}

export interface Conversation {
  id: string;
  title: string;
  created_at: string;
  messages: Message[];
  document_id: string;
  chat_history_id: string | null;
  modified_at: string;
  analysis_mode?: 'presales' | 'full';
  presales_id?: string;
  p1_blockers?: P1Blocker[];
  kickstart_questions?: KickstartQuestion[];
  blind_spots?: unknown;
  readiness?: ReadinessResult;
  contradictions?: Contradiction[];
  vague_answers?: VagueAnswer[];
  assumptions?: Assumption[];
}
