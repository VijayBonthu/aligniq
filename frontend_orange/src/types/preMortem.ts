export type Severity = 'high' | 'med' | 'low';
export type EvidenceType = 'risk' | 'assumption' | 'open_question' | 'section';
export type ItemStatus = 'open' | 'added_to_client_qs' | 'tracked_as_change';
export type TurnKind = 'starter' | 'user_question';
export type PanelistKind = 'default' | 'custom';
export type ItemAction = 'add_to_client_qs' | 'track_as_change';
export type ThreadStatus = 'ready' | 'empty' | 'report_not_ready';

export interface EvidenceRef {
  type: EvidenceType;
  ref_index: number | null;
  label: string;
}

export interface Item {
  id: string;
  severity: Severity;
  point: string;
  counter_response: string;
  evidence: EvidenceRef[];
  status: ItemStatus;
}

export interface TurnResponse {
  panelist_id: string;
  items: Item[];
}

export interface Turn {
  id: string;
  ts: string;
  kind: TurnKind;
  user_message: string;
  responses: TurnResponse[];
}

export interface Panelist {
  id: string;
  label: string;
  kind: PanelistKind;
  concern?: string;
}

export interface Thread {
  report_version_id: string;
  model: string;
  panelists: Panelist[];
  turns: Turn[];
}

export interface ThreadResponse {
  status: ThreadStatus;
  thread: Thread | null;
}

export interface ItemActionResult {
  already_applied?: boolean;
  status?: ItemStatus;
  appended_question?: string;
  total_open_questions?: number;
  pending_change_status?: string;
  pending_change_id?: string;
}

export interface Sources {
  key_risks: unknown[];
  critical_assumptions: unknown[];
  open_questions_for_client: unknown[];
}
