import { useCallback, useEffect, useState } from 'react';
import { toast } from 'react-hot-toast';
import {
  getJiraStatus,
  connectJira,
  listJiraProjects,
  listJiraEpics,
  listJiraChildren,
  searchJiraIssues,
  createJiraIssue,
  searchJiraUsers,
  sendDeliverableToJira,
  type JiraProject,
  type JiraIssue,
  type JiraUser,
} from '../../services/chatActionsService';
import LockedFeature from '../billing/LockedFeature';

type Format = 'pdf' | 'docx';
type Mode = 'new' | 'existing';

interface Props {
  open: boolean;
  onClose: () => void;
  defaultTitle: string;
  /** Builds the curated deliverable as a Blob in the chosen format (PDF/DOCX). */
  buildBlob: (format: Format) => Promise<{ blob: Blob; filename: string }>;
}

interface SendResult {
  key: string;
  browse_url?: string;
  attachment?: { filename?: string; browse_url?: string };
}

export default function JiraSendPanel({ open, onClose, defaultTitle, buildBlob }: Props) {
  const [status, setStatus] = useState<'checking' | 'connected' | 'disconnected'>('checking');
  const [connecting, setConnecting] = useState(false);

  const [projects, setProjects] = useState<JiraProject[]>([]);
  const [projectKey, setProjectKey] = useState('');

  const [mode, setMode] = useState<Mode>('new');
  const [newType, setNewType] = useState('Task');
  const [summary, setSummary] = useState(defaultTitle);
  const [parentEpic, setParentEpic] = useState(''); // optional: create the new story/task under this epic

  // Attach-target navigator (existing): Epics → drill into one → its stories/tasks.
  const [epics, setEpics] = useState<JiraIssue[]>([]);
  const [epicsLoading, setEpicsLoading] = useState(false);
  const [browseEpic, setBrowseEpic] = useState<JiraIssue | null>(null);
  const [children, setChildren] = useState<JiraIssue[]>([]);
  const [childrenLoading, setChildrenLoading] = useState(false);
  const [flatMode, setFlatMode] = useState(false); // project has no epics, or "browse all"
  const [flatIssues, setFlatIssues] = useState<JiraIssue[]>([]);
  const [issueFilter, setIssueFilter] = useState('');
  const [selectedIssue, setSelectedIssue] = useState('');

  const [format, setFormat] = useState<Format>('pdf');
  const [comment, setComment] = useState('');

  const [userQuery, setUserQuery] = useState('');
  const [users, setUsers] = useState<JiraUser[]>([]);
  const [assignee, setAssignee] = useState<JiraUser | null>(null);
  const [mentions, setMentions] = useState<JiraUser[]>([]);

  const [sending, setSending] = useState(false);
  const [result, setResult] = useState<SendResult | null>(null);

  const loadProjects = useCallback(async () => {
    try {
      const ps = await listJiraProjects();
      setProjects(ps);
      if (ps.length) setProjectKey((cur) => cur || ps[0].key);
    } catch {
      toast.error('Could not load Jira projects');
    }
  }, []);

  useEffect(() => {
    if (!open) return;
    setResult(null);
    setSummary(defaultTitle);
    setStatus('checking');
    getJiraStatus()
      .then((s) => {
        setStatus(s.connected ? 'connected' : 'disconnected');
        if (s.connected) void loadProjects();
      })
      .catch(() => setStatus('disconnected'));
  }, [open, defaultTitle, loadProjects]);

  // Load the project's epics — the top of the attach drill-down AND the "create under
  // epic" options. Falls back to a flat list when the project has no epics.
  useEffect(() => {
    if (!open || status !== 'connected' || !projectKey) return;
    setBrowseEpic(null);
    setSelectedIssue('');
    setFlatMode(false);
    setParentEpic('');
    setEpicsLoading(true);
    listJiraEpics(projectKey)
      .then((es) => { setEpics(es); if (es.length === 0) setFlatMode(true); })
      .catch(() => { setEpics([]); setFlatMode(true); })
      .finally(() => setEpicsLoading(false));
  }, [open, status, projectKey]);

  // Flat issue list (no epics, or user clicked "browse all").
  useEffect(() => {
    if (!open || status !== 'connected' || mode !== 'existing' || !flatMode || !projectKey) return;
    searchJiraIssues(projectKey).then(setFlatIssues).catch(() => setFlatIssues([]));
  }, [open, status, mode, flatMode, projectKey]);

  // Children of the drilled-into epic.
  useEffect(() => {
    if (!browseEpic) { setChildren([]); return; }
    setChildrenLoading(true);
    listJiraChildren(browseEpic.key)
      .then(setChildren)
      .catch(() => setChildren([]))
      .finally(() => setChildrenLoading(false));
  }, [browseEpic]);

  // People search (assignable in the project).
  useEffect(() => {
    if (status !== 'connected' || !projectKey || userQuery.trim().length < 1) {
      setUsers([]);
      return;
    }
    let cancelled = false;
    const t = window.setTimeout(() => {
      searchJiraUsers(projectKey, userQuery.trim())
        .then((u) => { if (!cancelled) setUsers(u); })
        .catch(() => { if (!cancelled) setUsers([]); });
    }, 250);
    return () => { cancelled = true; window.clearTimeout(t); };
  }, [status, projectKey, userQuery]);

  const handleConnect = async () => {
    setConnecting(true);
    try {
      await connectJira();
      setStatus('connected');
      await loadProjects();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not connect Jira');
    } finally {
      setConnecting(false);
    }
  };

  const toggleMention = (u: JiraUser) =>
    setMentions((cur) =>
      cur.some((m) => m.account_id === u.account_id)
        ? cur.filter((m) => m.account_id !== u.account_id)
        : [...cur, u],
    );

  const send = async () => {
    if (!projectKey) return;
    if (mode === 'existing' && !selectedIssue) { toast.error('Pick an epic, story or task to attach to'); return; }
    if (mode === 'new' && !summary.trim()) { toast.error('A summary is required'); return; }
    setSending(true);
    try {
      let key = selectedIssue;
      if (mode === 'new') {
        const created = await createJiraIssue({
          project_key: projectKey,
          summary: summary.trim(),
          issue_type: newType,
          description: 'Deliverable generated in GroundedIQ.',
          parent_key: newType !== 'Epic' && parentEpic ? parentEpic : undefined,
        });
        key = created.key;
      }
      const { blob, filename } = await buildBlob(format);
      const res = await sendDeliverableToJira(key, blob, filename, {
        comment: comment.trim() || undefined,
        assignee_id: assignee?.account_id,
        mentions: mentions.map((m) => ({ account_id: m.account_id, display_name: m.display_name })),
      });
      setResult(res as SendResult);
      toast.success(`Deliverable attached to ${key}`);
    } catch (err) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        (err instanceof Error ? err.message : 'Send to Jira failed');
      toast.error(detail);
    } finally {
      setSending(false);
    }
  };

  if (!open) return null;

  const filteredFlat = flatIssues.filter(
    (i) => !issueFilter.trim() || `${i.key} ${i.summary ?? ''}`.toLowerCase().includes(issueFilter.toLowerCase()),
  );

  return (
    <div style={overlay} onClick={onClose}>
      <div style={drawer} onClick={(e) => e.stopPropagation()}>
        <div style={header}>
          <span style={titleStyle}>Send deliverable to Jira</span>
          <button onClick={onClose} style={closeBtn} title="Close">✕</button>
        </div>

        {status === 'checking' ? (
          <div style={{ padding: 20 }}><p style={muted}>Checking Jira…</p></div>
        ) : status === 'disconnected' ? (
          <div style={{ padding: 20 }}>
            <p style={{ fontSize: 12.5, color: 'var(--fg-dim)', lineHeight: 1.6, margin: '0 0 14px' }}>
              Connect your Jira account to attach this deliverable. A secure Atlassian sign-in
              window opens and returns here automatically.
            </p>
            <button onClick={handleConnect} disabled={connecting} style={primaryWide}>
              {connecting ? 'Waiting for Jira…' : 'Connect Jira'}
            </button>
          </div>
        ) : result ? (
          <>
            <div style={{ flex: 1, overflowY: 'auto', padding: 16 }}>
              <p style={{ fontSize: 13, color: 'var(--fg)', margin: '0 0 12px' }}>Attached to Jira:</p>
              <div style={resultRow}>
                <span style={resultTag}>{result.attachment?.filename || 'FILE'}</span>
                <Link k={result.key} url={result.browse_url} />
              </div>
              {(assignee || mentions.length > 0) && (
                <p style={{ ...muted, marginTop: 10 }}>
                  {assignee ? `Assigned to ${assignee.display_name}. ` : ''}
                  {mentions.length ? `Notified ${mentions.length} ${mentions.length === 1 ? 'person' : 'people'}.` : ''}
                </p>
              )}
            </div>
            <div style={footer}>
              <button onClick={() => setResult(null)} style={ghostBtn}>Send another</button>
              <button onClick={onClose} style={primaryBtn}>Done</button>
            </div>
          </>
        ) : (
          <>
            <div style={{ flex: 1, overflowY: 'auto', padding: 16 }}>
              <label style={label}>Project</label>
              <select value={projectKey} onChange={(e) => setProjectKey(e.target.value)} style={selectWide}>
                {projects.map((p) => <option key={p.key} value={p.key}>{p.name} ({p.key})</option>)}
              </select>

              <label style={{ ...label, marginTop: 14 }}>Attach to</label>
              <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
                {(['new', 'existing'] as const).map((m) => (
                  <button key={m} onClick={() => setMode(m)} style={toggle(mode === m)}>
                    {m === 'new' ? 'New ticket' : 'Existing'}
                  </button>
                ))}
              </div>

              {mode === 'new' ? (
                <div style={{ marginTop: 10 }}>
                  <div style={{ display: 'flex', gap: 8 }}>
                    {(['Epic', 'Story', 'Task'] as const).map((t) => (
                      <button key={t} onClick={() => setNewType(t)} style={toggle(newType === t)}>{t}</button>
                    ))}
                  </div>
                  <input
                    value={summary}
                    onChange={(e) => setSummary(e.target.value)}
                    placeholder="Ticket summary"
                    style={{ ...input, marginTop: 8 }}
                  />
                  {newType !== 'Epic' && epics.length > 0 && (
                    <>
                      <label style={{ ...label, marginTop: 10 }}>Under epic (optional)</label>
                      <select value={parentEpic} onChange={(e) => setParentEpic(e.target.value)} style={selectWide}>
                        <option value="">— none —</option>
                        {epics.map((e) => <option key={e.key} value={e.key}>{e.summary || e.key} ({e.key})</option>)}
                      </select>
                    </>
                  )}
                </div>
              ) : (
                <div style={{ marginTop: 10 }}>
                  {epicsLoading ? (
                    <p style={muted}>Loading epics…</p>
                  ) : browseEpic ? (
                    <>
                      <button onClick={() => setBrowseEpic(null)} style={backLink}>← Epics</button>
                      <IssuePick
                        issue={browseEpic}
                        selected={selectedIssue === browseEpic.key}
                        onSelect={() => setSelectedIssue(browseEpic.key)}
                        labelOverride={`Attach to this epic · ${browseEpic.key}`}
                      />
                      <div style={{ maxHeight: 220, overflowY: 'auto', marginTop: 6 }}>
                        {childrenLoading ? (
                          <p style={muted}>Loading…</p>
                        ) : children.length === 0 ? (
                          <p style={muted}>No stories or tasks under this epic yet.</p>
                        ) : (
                          children.map((c) => (
                            <IssuePick key={c.key} issue={c} selected={selectedIssue === c.key} onSelect={() => setSelectedIssue(c.key)} />
                          ))
                        )}
                      </div>
                    </>
                  ) : flatMode ? (
                    <>
                      {epics.length > 0 && <button onClick={() => setFlatMode(false)} style={backLink}>← Epics</button>}
                      <input value={issueFilter} onChange={(e) => setIssueFilter(e.target.value)} placeholder="Filter tickets…" style={input} />
                      <div style={{ maxHeight: 220, overflowY: 'auto', marginTop: 6 }}>
                        {filteredFlat.map((i) => (
                          <IssuePick key={i.key} issue={i} selected={selectedIssue === i.key} onSelect={() => setSelectedIssue(i.key)} />
                        ))}
                        {flatIssues.length === 0 && <p style={muted}>No tickets in this project yet.</p>}
                      </div>
                    </>
                  ) : (
                    <>
                      <p style={{ ...muted, marginBottom: 6 }}>Pick an epic, or open it (▸) to attach to a story/task inside.</p>
                      <div style={{ maxHeight: 220, overflowY: 'auto' }}>
                        {epics.map((e) => (
                          <IssuePick
                            key={e.key}
                            issue={e}
                            selected={selectedIssue === e.key}
                            onSelect={() => setSelectedIssue(e.key)}
                            onOpen={() => setBrowseEpic(e)}
                          />
                        ))}
                      </div>
                      <button onClick={() => setFlatMode(true)} style={browseAllLink}>Browse all issues →</button>
                    </>
                  )}
                </div>
              )}

              <label style={{ ...label, marginTop: 16 }}>Format</label>
              <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
                {(['pdf', 'docx'] as const).map((f) => (
                  <button key={f} onClick={() => setFormat(f)} style={toggle(format === f)}>{f.toUpperCase()}</button>
                ))}
              </div>

              <label style={{ ...label, marginTop: 16 }}>Comment (optional)</label>
              <textarea
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                rows={2}
                placeholder="e.g. Deliverable v2 attached — please review."
                style={{ ...input, marginTop: 4, resize: 'vertical' }}
              />

              <label style={{ ...label, marginTop: 16 }}>People (assign / notify)</label>
              {(assignee || mentions.length > 0) && (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, margin: '6px 0' }}>
                  {assignee && <span style={chipAccent}>assignee: {assignee.display_name}
                    <button onClick={() => setAssignee(null)} style={chipX}>×</button></span>}
                  {mentions.map((m) => (
                    <span key={m.account_id} style={chip}>@{m.display_name}
                      <button onClick={() => toggleMention(m)} style={chipX}>×</button></span>
                  ))}
                </div>
              )}
              <input
                value={userQuery}
                onChange={(e) => setUserQuery(e.target.value)}
                placeholder="Search teammates…"
                style={{ ...input, marginTop: 4 }}
              />
              {users.length > 0 && (
                <div style={{ maxHeight: 150, overflowY: 'auto', marginTop: 6 }}>
                  {users.map((u) => (
                    <div key={u.account_id} style={userRow}>
                      <span style={{ flex: 1, minWidth: 0, fontSize: 12, color: 'var(--fg)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {u.display_name}{u.email ? <span style={{ color: 'var(--fg-muted)' }}> · {u.email}</span> : null}
                      </span>
                      <button onClick={() => setAssignee(u)} style={miniBtn(assignee?.account_id === u.account_id)}>assign</button>
                      <button onClick={() => toggleMention(u)} style={miniBtn(mentions.some((m) => m.account_id === u.account_id))}>cc</button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div style={footer}>
              <button onClick={onClose} style={ghostBtn}>Cancel</button>
              <LockedFeature feature="jira">
                <button onClick={send} disabled={sending || !projectKey} style={primaryBtn}>
                  {sending ? 'Sending…' : `Attach ${format.toUpperCase()} → Jira`}
                </button>
              </LockedFeature>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function IssuePick({
  issue, selected, onSelect, onOpen, labelOverride,
}: { issue: JiraIssue; selected: boolean; onSelect: () => void; onOpen?: () => void; labelOverride?: string }) {
  return (
    <div style={{ ...pickRow, borderColor: selected ? 'var(--accent)' : 'var(--border)', background: selected ? 'var(--accent-soft)' : 'var(--surface-2)' }}>
      <button onClick={onSelect} style={pickMain}>
        <TypeBadge type={issue.issue_type} />
        <span style={keyTag}>{issue.key}</span>
        <span style={{ fontSize: 12, color: 'var(--fg)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {labelOverride || issue.summary}
        </span>
      </button>
      {onOpen && <button onClick={onOpen} style={drillBtn} title="Open — view stories/tasks">▸</button>}
    </div>
  );
}

function TypeBadge({ type }: { type?: string | null }) {
  const isEpic = (type || '').toLowerCase() === 'epic';
  const color = isEpic ? 'var(--accent)' : 'var(--fg-muted)';
  return (
    <span style={{
      fontFamily: 'var(--font-mono)', fontSize: 8.5, letterSpacing: '.04em', textTransform: 'uppercase',
      color, border: `1px solid ${color}`, borderRadius: 4, padding: '1px 5px', flexShrink: 0,
    }}>{type || 'issue'}</span>
  );
}

function Link({ k, url }: { k: string; url?: string }) {
  if (!url) return <span style={keyTag}>{k}</span>;
  return <a href={url} target="_blank" rel="noreferrer" style={{ ...keyTag, textDecoration: 'none' }}>{k} ↗</a>;
}

// ---- styles ----
const overlay: React.CSSProperties = {
  position: 'fixed', inset: 0, background: 'rgba(0,0,0,.4)', zIndex: 70,
  display: 'flex', justifyContent: 'flex-end',
};
const drawer: React.CSSProperties = {
  width: 'min(440px, 100vw)', maxWidth: '100vw', height: '100%', background: 'var(--surface)',
  borderLeft: '1px solid var(--border)', display: 'flex', flexDirection: 'column',
  animation: 'slideInRight .2s ease',
};
const header: React.CSSProperties = {
  height: 48, flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'space-between',
  padding: '0 14px', borderBottom: '1px solid var(--border)',
};
const titleStyle: React.CSSProperties = { fontSize: 13, fontWeight: 600, color: 'var(--fg)', fontFamily: 'var(--font-sans)' };
const closeBtn: React.CSSProperties = { background: 'none', border: 'none', color: 'var(--fg-muted)', cursor: 'pointer', fontSize: 13 };
const muted: React.CSSProperties = { fontSize: 12, color: 'var(--fg-muted)', lineHeight: 1.5, margin: 0 };
const label: React.CSSProperties = {
  display: 'block', fontFamily: 'var(--font-mono)', fontSize: 9.5, letterSpacing: '.08em',
  textTransform: 'uppercase', color: 'var(--fg-muted)',
};
const selectWide: React.CSSProperties = {
  width: '100%', boxSizing: 'border-box', marginTop: 4, background: 'var(--surface)',
  border: '1px solid var(--border-strong)', borderRadius: 8, color: 'var(--fg)', fontSize: 12, padding: '7px 8px',
};
const input: React.CSSProperties = {
  width: '100%', boxSizing: 'border-box', background: 'var(--surface)', border: '1px solid var(--border-strong)',
  borderRadius: 8, color: 'var(--fg)', fontSize: 12.5, fontFamily: 'var(--font-sans)', padding: '7px 8px',
};
const footer: React.CSSProperties = {
  flexShrink: 0, display: 'flex', gap: 8, padding: 14, borderTop: '1px solid var(--border)', background: 'var(--surface-2)',
};
const primaryBtn: React.CSSProperties = {
  flex: 2, background: 'var(--accent)', color: 'var(--accent-ink)', border: 'none', borderRadius: 8,
  fontSize: 12.5, fontWeight: 600, padding: '9px', cursor: 'pointer',
};
const primaryWide: React.CSSProperties = { ...primaryBtn, width: '100%', flex: 'unset' };
const ghostBtn: React.CSSProperties = {
  flex: 1, background: 'transparent', border: '1px solid var(--border-strong)', borderRadius: 8,
  color: 'var(--fg-dim)', fontSize: 12.5, padding: '9px', cursor: 'pointer',
};
const pickRow: React.CSSProperties = {
  display: 'flex', alignItems: 'center', gap: 6, width: '100%',
  border: '1px solid var(--border)', borderRadius: 8, padding: '7px 8px', marginBottom: 6,
};
const pickMain: React.CSSProperties = {
  flex: 1, minWidth: 0, display: 'flex', alignItems: 'center', gap: 8,
  background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left', padding: 0,
};
const drillBtn: React.CSSProperties = {
  flexShrink: 0, background: 'transparent', border: '1px solid var(--border-strong)', borderRadius: 6,
  color: 'var(--fg-dim)', cursor: 'pointer', fontSize: 12, padding: '2px 8px',
};
const backLink: React.CSSProperties = {
  background: 'none', border: 'none', color: 'var(--accent)', cursor: 'pointer', fontSize: 11.5,
  fontFamily: 'var(--font-mono)', padding: '0 0 8px', display: 'block',
};
const browseAllLink: React.CSSProperties = {
  background: 'none', border: 'none', color: 'var(--fg-muted)', cursor: 'pointer', fontSize: 11,
  fontFamily: 'var(--font-mono)', padding: '8px 0 0',
};
const userRow: React.CSSProperties = {
  display: 'flex', alignItems: 'center', gap: 6, padding: '6px 0', borderBottom: '1px solid var(--border)',
};
const keyTag: React.CSSProperties = { fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--accent)', fontWeight: 600, flexShrink: 0 };
const resultRow: React.CSSProperties = { display: 'flex', alignItems: 'center', gap: 8, padding: '7px 0' };
const resultTag: React.CSSProperties = {
  fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '.04em', color: 'var(--accent)',
  border: '1px solid var(--accent)', borderRadius: 999, padding: '2px 7px', maxWidth: 200,
  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
};
const chip: React.CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: 4, background: 'var(--surface-2)',
  border: '1px solid var(--border-strong)', borderRadius: 999, color: 'var(--fg-dim)',
  fontSize: 10.5, fontFamily: 'var(--font-mono)', padding: '2px 8px',
};
const chipAccent: React.CSSProperties = { ...chip, background: 'var(--accent-soft)', border: '1px solid var(--accent)', color: 'var(--accent)' };
const chipX: React.CSSProperties = { background: 'none', border: 'none', color: 'inherit', cursor: 'pointer', fontSize: 12, lineHeight: 1, padding: 0 };

function toggle(active: boolean): React.CSSProperties {
  return {
    flex: 1, padding: '7px', borderRadius: 8, fontSize: 11.5, cursor: 'pointer',
    fontFamily: 'var(--font-mono)', letterSpacing: '.04em', textTransform: 'uppercase',
    border: `1px solid ${active ? 'var(--accent)' : 'var(--border-strong)'}`,
    background: active ? 'var(--accent-soft)' : 'transparent',
    color: active ? 'var(--accent)' : 'var(--fg-dim)',
  };
}
function miniBtn(active: boolean): React.CSSProperties {
  return {
    flexShrink: 0, fontSize: 10, fontFamily: 'var(--font-mono)', letterSpacing: '.04em',
    padding: '3px 8px', borderRadius: 999, cursor: 'pointer',
    border: `1px solid ${active ? 'var(--accent)' : 'var(--border-strong)'}`,
    background: active ? 'var(--accent-soft)' : 'transparent',
    color: active ? 'var(--accent)' : 'var(--fg-dim)',
  };
}
