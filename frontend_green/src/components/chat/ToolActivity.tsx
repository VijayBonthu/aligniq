// Renders what the chat agent is *doing* while it streams. The streaming hook
// already emits tool_start/tool_result; ChatView was dropping them, which made
// the agent feel like a black box. Friendly labels keep raw tool names + JSON
// out of the user's face.

const TOOL_LABELS: Record<string, string> = {
  get_report_section: 'Reading the report',
  get_diagrams: 'Pulling the diagram',
  list_report_sections: 'Scanning report sections',
  search_document: 'Searching the document',
  search_report_section: 'Searching the report',
  get_risks_and_mitigations: 'Gathering risks',
  get_pending_changes: 'Checking queued changes',
  find_duplicate_changes: 'Checking for duplicate changes',
  detect_conflicts: 'Checking for conflicts',
  get_report_versions: 'Reading version history',
  compare_report_versions: 'Comparing versions',
  suggest_optimization: 'Working up an optimization',
  analyze_cost_reduction: 'Analyzing cost reductions',
  analyze_timeline_acceleration: 'Analyzing the timeline',
  prepare_client_meeting_brief: 'Preparing a client-meeting brief',
  prepare_executive_summary: 'Preparing an executive summary',
  get_technical_deep_dive: 'Pulling a technical deep-dive',
  get_implementation_gotchas: 'Collecting implementation gotchas',
  get_project_blind_spots: 'Surfacing blind spots',
  get_project_insights: 'Extracting project insights',
  add_pending_change: 'Queuing the change',
  remove_pending_change: 'Removing the change',
  remove_last_pending_change: 'Removing the last change',
  clear_all_pending_changes: 'Clearing queued changes',
  merge_pending_changes: 'Merging changes',
  update_pending_change: 'Updating the change',
  regenerate_report: 'Regenerating the report',
  rollback_report: 'Rolling back the report',
  set_default_report: 'Setting the default version',
  firm_project_search: "Searching the firm's past projects",
  push_to_jira: 'Pushing to Jira',
};

export function toolLabel(name: string | null | undefined): string {
  if (!name) return 'Working';
  return TOOL_LABELS[name] || 'Working';
}

export default function ToolActivity({
  tool,
  status,
}: {
  tool: string | null;
  status: 'idle' | 'running' | 'completed' | 'error';
}) {
  if (!tool || status !== 'running') return null;
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        margin: '6px auto',
        width: 'fit-content',
        padding: '4px 12px',
        borderRadius: 999,
        background: 'var(--surface-2)',
        border: '1px solid var(--border)',
        fontFamily: 'var(--font-mono)',
        fontSize: 11,
        color: 'var(--fg-dim)',
        letterSpacing: '.04em',
      }}
    >
      <span
        style={{
          width: 11,
          height: 11,
          border: '2px solid var(--border-strong)',
          borderTopColor: 'var(--accent)',
          borderRadius: '50%',
          animation: 'spin 1s linear infinite',
        }}
      />
      {toolLabel(tool)}…
    </div>
  );
}
