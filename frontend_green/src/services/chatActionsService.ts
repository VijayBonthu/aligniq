import api from './api';

// ---- Pending changes ------------------------------------------------------

export interface PendingChange {
  id: string;
  user_request?: string;
  target_section?: string;
  change_type?: string;
  type?: string;
  status?: string;
}

export interface PendingChangesSummary {
  changes: PendingChange[];
  count: number;
  has_conflicts: boolean;
  conflicts: Array<{ description?: string }>;
}

export async function listPendingChanges(chatHistoryId: string): Promise<PendingChangesSummary> {
  const { data } = await api.get(`/pending-changes/${chatHistoryId}`);
  return {
    changes: Array.isArray(data?.changes) ? data.changes : [],
    count: data?.count ?? data?.total ?? (Array.isArray(data?.changes) ? data.changes.length : 0),
    has_conflicts: Boolean(data?.has_conflicts),
    conflicts: Array.isArray(data?.conflicts) ? data.conflicts : [],
  };
}

export async function addPendingChange(
  chatHistoryId: string,
  body: { user_request: string; target_section?: string; change_type?: string },
) {
  const { data } = await api.post(`/pending-changes/${chatHistoryId}`, body);
  return data;
}

export async function removePendingChange(chatHistoryId: string, changeId: string) {
  const { data } = await api.delete(`/pending-changes/${chatHistoryId}/${changeId}`);
  return data;
}

/** Edit a queued change in place (text / target section / change type). */
export async function updatePendingChange(
  chatHistoryId: string,
  changeId: string,
  updates: { user_request?: string; target_section?: string; change_type?: string },
) {
  const { data } = await api.put(`/pending-changes/${chatHistoryId}/${changeId}`, updates);
  return data;
}

export async function clearPendingChanges(chatHistoryId: string) {
  const { data } = await api.delete(`/pending-changes/${chatHistoryId}`);
  return data;
}

/** Async regenerate applying queued changes. Returns 202; track via /full-pipeline/status. */
export async function regenerateReport(chatHistoryId: string) {
  const { data } = await api.post(`/report/regenerate/${chatHistoryId}`);
  return data as {
    run_id: string;
    chat_history_id: string;
    status: string;
    current_stage: string | null;
    applied_changes?: number;
  };
}

// ---- Versions -------------------------------------------------------------

export interface ReportVersionMeta {
  version_number: number;
  created_at?: string;
  label?: string;
  summary?: string;
  changelog_summary?: string;
  is_default?: boolean;
  is_latest?: boolean;
  is_client_signoff?: boolean;
  signoff_at?: string | null;
  changes_applied?: unknown[];
}

export interface TechSwap {
  layer: string;
  type: 'added' | 'removed' | 'changed';
  from: string | null;
  to: string | null;
  rationale?: string | null;
  confidence?: string | null;
}

export interface TeamMember {
  label: string;
  role?: string | null;
  seniority?: string | null;
}

export interface TeamDelta {
  a_count: number;
  b_count: number;
  a_fte: number | null;
  b_fte: number | null;
  added: TeamMember[];
  removed: TeamMember[];
}

export interface StaffingDelta {
  new_gaps: Array<{ needed_role?: string | null; recommendation?: string | null; impact?: string | null }>;
  resolved_gaps: Array<string | null>;
}

export interface MilestoneChange {
  name: string;
  a_low: number; a_high: number; b_low: number; b_high: number;
}

export interface TimelineMilestoneDelta {
  changed: MilestoneChange[];
  added: string[];
  removed: string[];
}

export interface DecisionDelta {
  cost: {
    a_low: number; a_high: number; b_low: number; b_high: number;
    delta_low: number; delta_high: number; pct: number | null;
  } | null;
  timeline: {
    a_low: number; a_high: number; b_low: number; b_high: number;
    delta_low: number; delta_high: number;
  } | null;
  tech_swaps: TechSwap[];
  verdict: { from: string | null; to: string | null } | null;
  team?: TeamDelta | null;
  staffing?: StaffingDelta | null;
  timeline_milestones?: TimelineMilestoneDelta | null;
}

export interface VersionDiff {
  version_a: number;
  version_b: number;
  stats?: {
    lines_added?: number;
    lines_removed?: number;
    chars_in_a?: number;
    chars_in_b?: number;
  };
  summary_a?: string;
  summary_b?: string;
  changelog_a?: string;
  changelog_b?: string;
  decision_delta?: DecisionDelta | null;
  changes_applied?: Array<Record<string, unknown>>;
}

/** One version's computed comparable metrics (from the typed Contract). */
export interface VersionMetric {
  version: number;
  is_default?: boolean;
  changelog?: string | null;
  created_at?: string | null;
  has_contract?: boolean;
  cost_low?: number | null;
  cost_high?: number | null;
  timeline_weeks_low?: number | null;
  timeline_weeks_high?: number | null;
  verdict?: string | null;
  verdict_confidence?: string | null;
  headline_tech?: Record<string, string>;
  team_count?: number | null;
  team_fte?: number | null;
  staffing_gap_count?: number | null;
  exec_summary?: string;
}

export interface VersionSection {
  id: string;
  heading: string;
  level: number;
  kind: string;
  has_diagram: boolean;
  raw_markdown: string;
}

export async function listVersions(chatHistoryId: string): Promise<ReportVersionMeta[]> {
  const { data } = await api.get(`/report-versions/${chatHistoryId}`);
  return Array.isArray(data?.versions) ? data.versions : [];
}

export async function compareVersions(chatHistoryId: string, versionA: number, versionB: number): Promise<VersionDiff> {
  const { data } = await api.get(`/report-versions/${chatHistoryId}/diff/${versionA}/${versionB}`);
  return data as VersionDiff;
}

/** Computed comparable metrics across all versions (or a subset). Powers the compare matrix + ranking. */
export async function getVersionMetrics(chatHistoryId: string, versions?: number[]): Promise<VersionMetric[]> {
  const qs = versions && versions.length ? `?versions=${versions.join(',')}` : '';
  const { data } = await api.get(`/report-versions/${chatHistoryId}/metrics${qs}`);
  return Array.isArray(data?.metrics) ? data.metrics : [];
}

/** Parsed sections of one version (with raw markdown) for the side-by-side picker. */
export async function getVersionSections(chatHistoryId: string, versionNumber: number): Promise<VersionSection[]> {
  const { data } = await api.get(`/report-versions/${chatHistoryId}/sections/${versionNumber}`);
  return Array.isArray(data?.sections) ? data.sections : [];
}

/** Mark a version active/default. Chat answers from it + vector store re-embeds. */
export async function setDefaultVersion(chatHistoryId: string, versionNumber: number) {
  const { data } = await api.post(`/report-versions/${chatHistoryId}/default/${versionNumber}`);
  return data;
}

export async function rollbackVersion(chatHistoryId: string, versionNumber: number) {
  const { data } = await api.post(`/report-versions/${chatHistoryId}/rollback/${versionNumber}`);
  return data;
}

/** Pin one version as the client-signoff baseline (one per project). The change-order draft computes against it. */
export async function signoffVersion(chatHistoryId: string, versionNumber: number) {
  const { data } = await api.post(`/report-versions/${chatHistoryId}/signoff/${versionNumber}`);
  return data;
}

export interface ChangeOrder {
  baseline_version: number;
  current_version: number;
  markdown?: string;
  pdf_base64?: string;
  filename?: string;
}

/** Deterministic change-order draft: signed baseline vs current version. format 'md' | 'pdf'. */
export async function getChangeOrder(chatHistoryId: string, format: 'md' | 'pdf' = 'md'): Promise<ChangeOrder> {
  const { data } = await api.get(`/report-versions/${chatHistoryId}/change-order?format=${format}`);
  return data as ChangeOrder;
}

// ---- Edit-without-regen (WS-2): cost editor + answer-question ----

export interface CostLineEdit {
  workstream: string;
  role: string;
  seniority?: string;
  region?: string;
  hours_low: number;
  hours_high: number;
  rate_usd: number;
  rate_card_ref?: string;
}

export interface CostTotals {
  subtotal_low: number; subtotal_high: number;
  grand_low: number; grand_high: number;
  worst_case_low: number; worst_case_high: number;
  contingency_pct: number; adverse_sensitivity_pct: number;
}

export interface ContractCost {
  version_number: number | null;
  cost_lines: CostLineEdit[];
  contingency_pct: number;
  cost_sensitivity: { condition: string; delta_pct: number }[];
  totals: CostTotals;
}

/** Current cost lines + totals for the active version (seeds the cost editor). 409 if legacy. */
export async function getContractCost(chatHistoryId: string): Promise<ContractCost> {
  const { data } = await api.get(`/report-contract/${chatHistoryId}/cost`);
  return data as ContractCost;
}

/** Recompute totals from edited lines WITHOUT saving (live editor preview). */
export async function previewContractCost(
  chatHistoryId: string, costLines: CostLineEdit[], contingencyPct: number,
): Promise<{ totals: CostTotals; cost_lines: CostLineEdit[]; rate_notes: string[] }> {
  const { data } = await api.patch(
    `/report-contract/${chatHistoryId}/cost?preview=true`,
    { cost_lines: costLines, contingency_pct: contingencyPct },
  );
  return data;
}

/** Save edited cost lines as a new version (deterministic, no pipeline regen). */
export async function saveContractCost(
  chatHistoryId: string, costLines: CostLineEdit[], contingencyPct: number,
): Promise<{ version_number: number; totals: CostTotals; cost_table_replaced: boolean }> {
  const { data } = await api.patch(
    `/report-contract/${chatHistoryId}/cost`,
    { cost_lines: costLines, contingency_pct: contingencyPct },
  );
  return data;
}

/** Answer an open question inline; queues a reviewable change for the next regenerate. */
export async function answerOpenQuestion(chatHistoryId: string, question: string, answer: string) {
  const { data } = await api.post(`/report-contract/${chatHistoryId}/answer-question`, { question, answer });
  return data;
}

// ---- Jira delivery handoff ------------------------------------------------

export interface JiraProject {
  key: string;
  name: string;
  id?: string;
}

export interface JiraIssue {
  key: string;
  summary?: string | null;
  status?: string | null;
  issue_type?: string | null;
  labels: string[];
  parent_key?: string | null;
  browse_url?: string;
}

export interface JiraReportItem {
  id: string;
  summary: string;
  description: string;
}

export interface JiraTransition {
  id: string;
  name: string;
  to_status?: string | null;
}

export interface JiraPushResult {
  epic_key: string;
  epic?: { key: string; browse_url?: string };
  issue_keys: string[];
  issues: Array<{ key: string; browse_url?: string }>;
  scope: string;
  project_key: string;
}

export async function listJiraProjects(): Promise<JiraProject[]> {
  const { data } = await api.get('/jira/projects');
  return Array.isArray(data?.projects) ? data.projects : [];
}

/** Epics in a project — for the "attach stories to an existing epic" picker. */
export async function listJiraEpics(projectKey: string): Promise<JiraIssue[]> {
  const { data } = await api.get('/jira/epics', { params: { project_key: projectKey } });
  return Array.isArray(data?.epics) ? data.epics : [];
}

/** Browse issues in a project (most-recently-updated first) for the manage tab. */
export async function searchJiraIssues(projectKey: string): Promise<JiraIssue[]> {
  const { data } = await api.get('/jira/issues/search', { params: { project_key: projectKey } });
  return Array.isArray(data?.issues) ? data.issues : [];
}

/** Child issues (stories/tasks/sub-tasks) under an epic/story — for the drill-down picker. */
export async function listJiraChildren(parentKey: string): Promise<JiraIssue[]> {
  const { data } = await api.get(`/jira/issue/${parentKey}/children`);
  return Array.isArray(data?.issues) ? data.issues : [];
}

/** Preview what a push would create — derives from the report, creates nothing in Jira. */
export async function getJiraReportItems(
  chatHistoryId: string,
  scope: 'risks' | 'sections',
): Promise<{ exec_summary: string; items: JiraReportItem[]; scope: string }> {
  const { data } = await api.get('/jira/report-items', {
    params: { chat_history_id: chatHistoryId, scope },
  });
  return {
    exec_summary: data?.exec_summary ?? '',
    items: Array.isArray(data?.items) ? data.items : [],
    scope: data?.scope ?? scope,
  };
}

export async function pushToJira(
  chatHistoryId: string,
  body: {
    project_key: string;
    scope?: 'risks' | 'sections';
    section_ids?: string[];
    items?: Array<{ summary: string; description: string }>;
    epic_key?: string;
    labels?: string[];
  },
): Promise<JiraPushResult> {
  const { data } = await api.post('/jira/create-from-report', {
    chat_history_id: chatHistoryId,
    ...body,
  });
  return data as JiraPushResult;
}

/** Edit an existing issue's summary and/or description. */
export async function updateJiraIssue(
  issueKey: string,
  updates: { summary?: string; description?: string },
) {
  const { data } = await api.put(`/jira/issue/${issueKey}`, updates);
  return data as { key: string; browse_url?: string };
}

/** Add and/or remove labels (tags) on an issue. */
export async function setJiraLabels(
  issueKey: string,
  body: { add?: string[]; remove?: string[] },
) {
  const { data } = await api.post(`/jira/issue/${issueKey}/labels`, body);
  return data as { key: string; browse_url?: string };
}

export async function addJiraComment(issueKey: string, commentBody: string) {
  const { data } = await api.post(`/jira/issue/${issueKey}/comment`, { body: commentBody });
  return data as { id?: string; key: string; browse_url?: string };
}

export async function getJiraTransitions(issueKey: string): Promise<JiraTransition[]> {
  const { data } = await api.get(`/jira/issue/${issueKey}/transitions`);
  return Array.isArray(data?.transitions) ? data.transitions : [];
}

export async function transitionJiraIssue(issueKey: string, transitionId: string) {
  const { data } = await api.post(`/jira/issue/${issueKey}/transition`, { transition_id: transitionId });
  return data as { key: string; browse_url?: string };
}

// ---- Deliverable → Jira (create target, find people, attach file) ---------

export interface JiraUser {
  account_id: string;
  display_name?: string | null;
  email?: string | null;
  avatar_url?: string | null;
  active?: boolean;
}

/** Create a single issue/epic — the "new target" for a deliverable push. */
export async function createJiraIssue(body: {
  project_key: string;
  summary: string;
  description?: string;
  issue_type?: string;
  parent_key?: string;
}): Promise<{ key: string; browse_url?: string }> {
  const { data } = await api.post('/jira/issue', body);
  return data as { key: string; browse_url?: string };
}

/** Search users assignable in a project — for the assign / @mention picker. */
export async function searchJiraUsers(projectKey: string, query: string): Promise<JiraUser[]> {
  const { data } = await api.get('/jira/users/search', { params: { project_key: projectKey, query } });
  return Array.isArray(data?.users) ? data.users : [];
}

/** Attach the deliverable file to an issue, optionally assigning + posting a comment
 * that @mentions teammates — the Deliverable Builder's "Send to Jira". */
export async function sendDeliverableToJira(
  issueKey: string,
  file: Blob,
  filename: string,
  opts: {
    comment?: string;
    assignee_id?: string;
    mentions?: Array<{ account_id: string; display_name?: string | null }>;
  } = {},
): Promise<{ key: string; browse_url?: string; attachment?: { id?: string; filename?: string; browse_url?: string } }> {
  const form = new FormData();
  form.append('file', file, filename);
  if (opts.comment) form.append('comment', opts.comment);
  if (opts.assignee_id) form.append('assignee_id', opts.assignee_id);
  if (opts.mentions && opts.mentions.length) form.append('mention_ids', JSON.stringify(opts.mentions));
  const { data } = await api.post(`/jira/issue/${issueKey}/attach`, form);
  return data;
}

// ---- Jira OAuth connect ---------------------------------------------------

export interface JiraConnectionStatus {
  connected: boolean;
  email?: string | null;
  account_id?: string | null;
}

/** Server-side connection status (tokens live in the DB; nothing in the browser). */
export async function getJiraStatus(): Promise<JiraConnectionStatus> {
  const { data } = await api.get('/jira/status');
  return { connected: Boolean(data?.connected), email: data?.email ?? null, account_id: data?.account_id ?? null };
}

/** Disconnect Jira for the current user (deletes server-side tokens). */
export async function disconnectJira(): Promise<void> {
  await api.post('/jira/disconnect');
}

/**
 * Run the Jira OAuth popup flow. The backend stores the tokens server-side keyed to the
 * user, so the popup carries NOTHING back — we just open it and poll GET /jira/status
 * until the server reports connected (or the popup closes / a timeout elapses). No
 * postMessage, no client token, no COOP/origin fragility.
 */
export async function connectJira(): Promise<void> {
  const { data } = await api.get('/auth/jira/login');
  const url: string | undefined = data?.url;
  if (!url) throw new Error('Could not start Jira sign-in');

  const popup = window.open(url, 'jira_oauth', 'width=620,height=760');
  if (!popup) throw new Error('Popup blocked — allow popups for this site and retry');

  return new Promise<void>((resolve, reject) => {
    let ticks = 0;
    let checking = false;
    const poll = window.setInterval(async () => {
      ticks += 1;
      if (!checking) {
        checking = true;
        try {
          const { connected } = await getJiraStatus();
          if (connected) { window.clearInterval(poll); resolve(); return; }
        } catch {
          /* transient — keep polling */
        } finally {
          checking = false;
        }
      }
      if (popup.closed) {
        // Give one last status check a beat to land, then decide.
        window.clearInterval(poll);
        getJiraStatus()
          .then(({ connected }) => (connected ? resolve() : reject(new Error('Jira sign-in window closed before finishing'))))
          .catch(() => reject(new Error('Jira sign-in window closed before finishing')));
      } else if (ticks > 200) { // ~5 min safety net (1.5s cadence)
        window.clearInterval(poll);
        reject(new Error('Jira sign-in timed out'));
      }
    }, 1500);
  });
}
