import { useCallback, useEffect, useMemo, useState } from 'react';
import { toast } from 'react-hot-toast';
import { isAxiosError } from 'axios';
import { friendlyError } from '../../services/api';
import {
  listJiraProjects,
  listJiraEpics,
  searchJiraIssues,
  getJiraReportItems,
  pushToJira,
  updateJiraIssue,
  setJiraLabels,
  addJiraComment,
  getJiraTransitions,
  transitionJiraIssue,
  connectJira,
  getJiraStatus,
  type JiraProject,
  type JiraIssue,
  type JiraTransition,
  type JiraPushResult,
} from '../../services/chatActionsService';

type Tab = 'push' | 'tickets';

interface Props {
  chatHistoryId: string;
  onClose: () => void;
}

// Always returns a string — friendlyError safely flattens an object `detail` so it can never
// reach toast.error() (which crashes on a non-string React child).
function errDetail(err: unknown, fallback: string): string {
  return friendlyError(err, fallback);
}

export default function JiraWorkspace({ chatHistoryId, onClose }: Props) {
  const [tab, setTab] = useState<Tab>('push');
  const [projects, setProjects] = useState<JiraProject[] | null>(null);
  const [projectKey, setProjectKey] = useState('');
  const [notConnected, setNotConnected] = useState(false);
  const [loading, setLoading] = useState(true);
  const [connecting, setConnecting] = useState(false);

  const loadProjects = useCallback(async () => {
    setLoading(true);
    try {
      const ps = await listJiraProjects();
      setProjects(ps);
      setNotConnected(false);
      if (ps.length) setProjectKey((cur) => cur || ps[0].key);
    } catch (err) {
      if (isAxiosError(err) && err.response?.status === 401) setNotConnected(true);
      else toast.error('Could not load Jira projects');
    } finally {
      setLoading(false);
    }
  }, []);

  // Check connection status first so a not-connected user sees the Connect prompt
  // immediately, instead of firing /jira/projects → 401 → a pointless app-token refresh.
  const init = useCallback(async () => {
    setLoading(true);
    try {
      const { connected } = await getJiraStatus();
      if (!connected) {
        setNotConnected(true);
        setLoading(false);
        return;
      }
      setNotConnected(false);
      await loadProjects();
    } catch {
      // Status check itself failed — fall back to attempting the project load.
      await loadProjects();
    }
  }, [loadProjects]);

  useEffect(() => {
    void init();
  }, [init]);

  const handleConnect = async () => {
    setConnecting(true);
    try {
      await connectJira();
      toast.success('Jira connected');
      await loadProjects();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not connect Jira');
    } finally {
      setConnecting(false);
    }
  };

  const projectName = useMemo(
    () => projects?.find((p) => p.key === projectKey)?.name || projectKey,
    [projects, projectKey],
  );

  return (
    <div style={overlay} onClick={onClose}>
      <div style={drawer} onClick={(e) => e.stopPropagation()}>
        <div style={header}>
          <span style={titleStyle}>
            Jira{projectName ? <span style={{ color: 'var(--fg-muted)', fontWeight: 400 }}> · {projectName}</span> : null}
          </span>
          <button onClick={onClose} style={closeBtn} title="Close">✕</button>
        </div>

        {notConnected ? (
          <div style={{ padding: 20 }}>
            <p style={{ fontSize: 12.5, color: 'var(--fg-dim)', lineHeight: 1.6, margin: '0 0 14px' }}>
              Connect your Jira account to push the report and manage tickets. A secure Atlassian
              sign-in window will open — approve access, and it returns here automatically.
            </p>
            <button onClick={handleConnect} disabled={connecting} style={primaryWide}>
              {connecting ? 'Waiting for Jira…' : 'Connect Jira'}
            </button>
          </div>
        ) : (
          <>
            <div style={tabBar}>
              {(['push', 'tickets'] as const).map((t) => (
                <button
                  key={t}
                  onClick={() => setTab(t)}
                  style={{
                    ...tabBtn,
                    color: tab === t ? 'var(--accent)' : 'var(--fg-dim)',
                    borderBottomColor: tab === t ? 'var(--accent)' : 'transparent',
                  }}
                >
                  {t === 'push' ? 'Push' : 'Tickets'}
                </button>
              ))}
            </div>

            <div style={projectBar}>
              <label style={miniLabel}>Project</label>
              {loading ? (
                <span style={muted}>Loading…</span>
              ) : (
                <select value={projectKey} onChange={(e) => setProjectKey(e.target.value)} style={selectWide}>
                  {(projects || []).map((p) => (
                    <option key={p.key} value={p.key}>{p.name} ({p.key})</option>
                  ))}
                </select>
              )}
            </div>

            {tab === 'push' ? (
              <PushTab chatHistoryId={chatHistoryId} projectKey={projectKey} />
            ) : (
              <TicketsTab projectKey={projectKey} />
            )}
          </>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Push tab — selectable / editable builder, then create epic + stories.
// ---------------------------------------------------------------------------

interface BuilderItem {
  id: string;
  summary: string;
  description: string;
  include: boolean;
  expanded: boolean;
}

function PushTab({ chatHistoryId, projectKey }: { chatHistoryId: string; projectKey: string }) {
  const [scope, setScope] = useState<'risks' | 'sections'>('risks');
  const [items, setItems] = useState<BuilderItem[]>([]);
  const [loadingItems, setLoadingItems] = useState(false);
  const [epicMode, setEpicMode] = useState<'new' | 'existing'>('new');
  const [epics, setEpics] = useState<JiraIssue[]>([]);
  const [epicKey, setEpicKey] = useState('');
  const [labels, setLabels] = useState<string[]>(['groundediq']);
  const [pushing, setPushing] = useState(false);
  const [result, setResult] = useState<JiraPushResult | null>(null);

  const loadItems = useCallback(async () => {
    setLoadingItems(true);
    setResult(null);
    try {
      const { items: raw } = await getJiraReportItems(chatHistoryId, scope);
      setItems(raw.map((it) => ({ ...it, include: true, expanded: false })));
    } catch (err) {
      toast.error(errDetail(err, 'Could not load report items'));
      setItems([]);
    } finally {
      setLoadingItems(false);
    }
  }, [chatHistoryId, scope]);

  useEffect(() => {
    void loadItems();
  }, [loadItems]);

  useEffect(() => {
    if (epicMode !== 'existing' || !projectKey) return;
    void (async () => {
      try {
        const es = await listJiraEpics(projectKey);
        setEpics(es);
        setEpicKey((cur) => cur || es[0]?.key || '');
      } catch {
        setEpics([]);
      }
    })();
  }, [epicMode, projectKey]);

  const patch = (id: string, up: Partial<BuilderItem>) =>
    setItems((cur) => cur.map((it) => (it.id === id ? { ...it, ...up } : it)));

  const selected = items.filter((it) => it.include);

  const push = async () => {
    if (!projectKey || !selected.length) return;
    if (epicMode === 'existing' && !epicKey) {
      toast.error('Pick an epic to attach to');
      return;
    }
    setPushing(true);
    try {
      const res = await pushToJira(chatHistoryId, {
        project_key: projectKey,
        scope,
        items: selected.map((it) => ({ summary: it.summary, description: it.description })),
        labels,
        ...(epicMode === 'existing' ? { epic_key: epicKey } : {}),
      });
      setResult(res);
      toast.success(`Created ${res.issue_keys.length} stories under ${res.epic_key}`);
    } catch (err) {
      toast.error(errDetail(err, 'Jira push failed'));
    } finally {
      setPushing(false);
    }
  };

  if (result) {
    return (
      <>
        <div style={{ flex: 1, overflowY: 'auto', padding: 14 }}>
          <p style={{ fontSize: 12.5, color: 'var(--fg)', margin: '0 0 10px' }}>
            Pushed to Jira — open the tickets:
          </p>
          <div style={resultRow}>
            <span style={resultTag}>EPIC</span>
            <IssueLink k={result.epic_key} url={result.epic?.browse_url} />
          </div>
          {result.issues.map((i) => (
            <div key={i.key} style={resultRow}>
              <span style={{ ...resultTag, color: 'var(--fg-muted)', borderColor: 'var(--border-strong)' }}>STORY</span>
              <IssueLink k={i.key} url={i.browse_url} />
            </div>
          ))}
        </div>
        <div style={footer}>
          <button onClick={() => { setResult(null); void loadItems(); }} style={regenBtn}>Push more →</button>
        </div>
      </>
    );
  }

  return (
    <>
      <div style={{ flex: 1, overflowY: 'auto', padding: 14 }}>
        <label style={miniLabel}>What to push</label>
        <div style={{ display: 'flex', gap: 8, margin: '4px 0 14px' }}>
          {(['risks', 'sections'] as const).map((s) => (
            <button key={s} onClick={() => setScope(s)} style={toggle(scope === s)}>{s}</button>
          ))}
        </div>

        <label style={miniLabel}>Epic</label>
        <div style={{ display: 'flex', gap: 8, margin: '4px 0 8px' }}>
          {(['new', 'existing'] as const).map((m) => (
            <button key={m} onClick={() => setEpicMode(m)} style={toggle(epicMode === m)}>
              {m === 'new' ? 'New epic' : 'Existing'}
            </button>
          ))}
        </div>
        {epicMode === 'existing' && (
          <select value={epicKey} onChange={(e) => setEpicKey(e.target.value)} style={{ ...selectWide, marginBottom: 8 }}>
            {epics.length === 0 && <option value="">No epics found</option>}
            {epics.map((e) => <option key={e.key} value={e.key}>{e.summary || e.key} ({e.key})</option>)}
          </select>
        )}

        <label style={{ ...miniLabel, marginTop: 6 }}>Tags</label>
        <div style={{ margin: '4px 0 14px' }}>
          <LabelChips labels={labels} onChange={setLabels} editable />
        </div>

        <label style={miniLabel}>
          Items {items.length ? `(${selected.length}/${items.length} selected)` : ''}
        </label>
        <div style={{ marginTop: 6 }}>
          {loadingItems ? (
            <p style={muted}>Loading items…</p>
          ) : items.length === 0 ? (
            <p style={muted}>Nothing to push for “{scope}”. Try the other scope.</p>
          ) : (
            items.map((it) => (
              <div key={it.id} style={itemRow}>
                <input
                  type="checkbox"
                  checked={it.include}
                  onChange={(e) => patch(it.id, { include: e.target.checked })}
                  style={{ marginTop: 5, accentColor: 'var(--accent)' }}
                />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <input
                    value={it.summary}
                    onChange={(e) => patch(it.id, { summary: e.target.value })}
                    style={summaryInput}
                  />
                  <button onClick={() => patch(it.id, { expanded: !it.expanded })} style={expandBtn}>
                    {it.expanded ? 'Hide details' : 'Edit details'}
                  </button>
                  {it.expanded && (
                    <textarea
                      value={it.description}
                      onChange={(e) => patch(it.id, { description: e.target.value })}
                      rows={4}
                      style={{ ...textarea, marginTop: 6 }}
                    />
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      <div style={footer}>
        <button onClick={push} disabled={pushing || !selected.length || !projectKey} style={regenBtn}>
          {pushing ? 'Pushing…' : `Create ${selected.length} ${epicMode === 'new' ? 'epic + ' : ''}stories →`}
        </button>
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------
// Tickets tab — browse a project, then update / tag / comment / transition.
// ---------------------------------------------------------------------------

function TicketsTab({ projectKey }: { projectKey: string }) {
  const [issues, setIssues] = useState<JiraIssue[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<JiraIssue | null>(null);

  const load = useCallback(async () => {
    if (!projectKey) return;
    setLoading(true);
    try {
      setIssues(await searchJiraIssues(projectKey));
    } catch (err) {
      toast.error(errDetail(err, 'Could not load Jira issues'));
      setIssues([]);
    } finally {
      setLoading(false);
    }
  }, [projectKey]);

  useEffect(() => {
    setSelected(null);
    void load();
  }, [load]);

  if (selected) {
    return <TicketEditor issue={selected} onBack={() => { setSelected(null); void load(); }} />;
  }

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: 14 }}>
      {loading ? (
        <p style={muted}>Loading tickets…</p>
      ) : !issues || issues.length === 0 ? (
        <p style={muted}>No tickets in this project yet.</p>
      ) : (
        issues.map((i) => (
          <button key={i.key} onClick={() => setSelected(i)} style={ticketRow}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
              <span style={ticketKey}>{i.key}</span>
              {i.status && <span style={statusPill}>{i.status}</span>}
            </div>
            <p style={ticketSummary}>{i.summary}</p>
            {i.labels.length > 0 && (
              <div style={{ marginTop: 6 }}><LabelChips labels={i.labels} /></div>
            )}
          </button>
        ))
      )}
    </div>
  );
}

function TicketEditor({ issue, onBack }: { issue: JiraIssue; onBack: () => void }) {
  const [summary, setSummary] = useState(issue.summary || '');
  const [description, setDescription] = useState('');
  const [labels, setLabels] = useState<string[]>(issue.labels || []);
  const [comment, setComment] = useState('');
  const [transitions, setTransitions] = useState<JiraTransition[]>([]);
  const [transitionId, setTransitionId] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void (async () => {
      try {
        const ts = await getJiraTransitions(issue.key);
        setTransitions(ts);
        setTransitionId(ts[0]?.id || '');
      } catch {
        setTransitions([]);
      }
    })();
  }, [issue.key]);

  const run = async (fn: () => Promise<unknown>, ok: string) => {
    setBusy(true);
    try {
      await fn();
      toast.success(ok);
    } catch (err) {
      toast.error(errDetail(err, 'Jira update failed'));
    } finally {
      setBusy(false);
    }
  };

  const saveFields = () => {
    const updates: { summary?: string; description?: string } = {};
    if (summary.trim() && summary !== issue.summary) updates.summary = summary.trim();
    if (description.trim()) updates.description = description.trim();
    if (!Object.keys(updates).length) { toast('Nothing changed'); return; }
    void run(() => updateJiraIssue(issue.key, updates), 'Ticket updated');
  };

  const changeLabels = async (next: string[]) => {
    const add = next.filter((l) => !labels.includes(l));
    const remove = labels.filter((l) => !next.includes(l));
    setLabels(next);
    if (!add.length && !remove.length) return;
    await run(() => setJiraLabels(issue.key, { add, remove }), 'Tags updated');
  };

  const postComment = () =>
    run(async () => {
      if (!comment.trim()) return;
      await addJiraComment(issue.key, comment.trim());
      setComment('');
    }, 'Comment added');

  const moveStatus = () =>
    run(async () => {
      if (!transitionId) return;
      await transitionJiraIssue(issue.key, transitionId);
    }, 'Status updated');

  return (
    <>
      <div style={{ flex: 1, overflowY: 'auto', padding: 14 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
          <button onClick={onBack} style={backBtn}>← Back</button>
          <IssueLink k={issue.key} url={issue.browse_url} />
          {issue.status && <span style={statusPill}>{issue.status}</span>}
        </div>

        <label style={miniLabel}>Summary</label>
        <input value={summary} onChange={(e) => setSummary(e.target.value)} style={{ ...summaryInput, marginTop: 4 }} />

        <label style={{ ...miniLabel, marginTop: 12 }}>Replace description (optional)</label>
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          rows={4}
          placeholder="Leave blank to keep the current description…"
          style={{ ...textarea, marginTop: 4 }}
        />
        <button onClick={saveFields} disabled={busy} style={{ ...smallPrimary, marginTop: 8 }}>Save fields</button>

        <label style={{ ...miniLabel, marginTop: 16 }}>Tags</label>
        <div style={{ marginTop: 4 }}>
          <LabelChips labels={labels} onChange={(n) => void changeLabels(n)} editable />
        </div>

        <label style={{ ...miniLabel, marginTop: 16 }}>Status</label>
        <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
          <select value={transitionId} onChange={(e) => setTransitionId(e.target.value)} style={selectWide}>
            {transitions.length === 0 && <option value="">No transitions</option>}
            {transitions.map((t) => (
              <option key={t.id} value={t.id}>{t.name}{t.to_status ? ` → ${t.to_status}` : ''}</option>
            ))}
          </select>
          <button onClick={moveStatus} disabled={busy || !transitionId} style={smallPrimary}>Move</button>
        </div>

        <label style={{ ...miniLabel, marginTop: 16 }}>Comment</label>
        <textarea
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          rows={3}
          placeholder="Add a comment to this ticket…"
          style={{ ...textarea, marginTop: 4 }}
        />
        <button onClick={postComment} disabled={busy || !comment.trim()} style={{ ...smallPrimary, marginTop: 8 }}>
          Add comment
        </button>
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------
// Shared bits
// ---------------------------------------------------------------------------

function IssueLink({ k, url }: { k: string; url?: string }) {
  if (!url) return <span style={ticketKey}>{k}</span>;
  return (
    <a href={url} target="_blank" rel="noreferrer" style={{ ...ticketKey, textDecoration: 'none' }}>
      {k} ↗
    </a>
  );
}

function LabelChips({
  labels, onChange, editable,
}: { labels: string[]; onChange?: (l: string[]) => void; editable?: boolean }) {
  const [draft, setDraft] = useState('');
  const add = () => {
    const v = draft.trim().replace(/\s+/g, '-');
    if (v && !labels.includes(v)) onChange?.([...labels, v]);
    setDraft('');
  };
  return (
    <div style={chipWrap}>
      {labels.map((l) => (
        <span key={l} style={chip}>
          {l}
          {editable && (
            <button onClick={() => onChange?.(labels.filter((x) => x !== l))} style={chipX} title="Remove">×</button>
          )}
        </span>
      ))}
      {editable && (
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); add(); } }}
          onBlur={add}
          placeholder="add tag…"
          style={chipInput}
        />
      )}
    </div>
  );
}

// ---- styles (mirrors PendingChangesPanel tokens) --------------------------

const overlay: React.CSSProperties = {
  position: 'fixed', inset: 0, background: 'rgba(0,0,0,.4)', zIndex: 60,
  display: 'flex', justifyContent: 'flex-end',
};
const drawer: React.CSSProperties = {
  width: 'min(460px, 100vw)', maxWidth: '100vw', height: '100%', background: 'var(--surface)',
  borderLeft: '1px solid var(--border)', display: 'flex', flexDirection: 'column',
  animation: 'slideInRight .2s ease',
};
const header: React.CSSProperties = {
  height: 48, flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'space-between',
  padding: '0 14px', borderBottom: '1px solid var(--border)',
};
const titleStyle: React.CSSProperties = { fontSize: 13, fontWeight: 600, color: 'var(--fg)', fontFamily: 'var(--font-sans)', minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' };
const closeBtn: React.CSSProperties = { background: 'none', border: 'none', color: 'var(--fg-muted)', cursor: 'pointer', fontSize: 13 };
const tabBar: React.CSSProperties = { flexShrink: 0, display: 'flex', gap: 4, padding: '0 14px', borderBottom: '1px solid var(--border)' };
const tabBtn: React.CSSProperties = {
  background: 'none', border: 'none', borderBottom: '2px solid transparent', padding: '10px 8px',
  fontSize: 12.5, fontWeight: 600, cursor: 'pointer', fontFamily: 'var(--font-sans)',
};
const projectBar: React.CSSProperties = {
  flexShrink: 0, display: 'flex', alignItems: 'center', gap: 8, padding: '10px 14px',
  borderBottom: '1px solid var(--border)', background: 'var(--surface-2)',
};
const miniLabel: React.CSSProperties = {
  display: 'block', fontFamily: 'var(--font-mono)', fontSize: 9.5, letterSpacing: '.08em',
  textTransform: 'uppercase', color: 'var(--fg-muted)',
};
const muted: React.CSSProperties = { fontSize: 12, color: 'var(--fg-muted)', lineHeight: 1.5 };
const selectWide: React.CSSProperties = {
  flex: 1, minWidth: 0, background: 'var(--surface)', border: '1px solid var(--border-strong)', borderRadius: 8,
  color: 'var(--fg)', fontSize: 12, padding: '7px 8px', boxSizing: 'border-box',
};
const textarea: React.CSSProperties = {
  width: '100%', background: 'var(--surface)', border: '1px solid var(--border-strong)', borderRadius: 8,
  color: 'var(--fg)', fontSize: 12.5, fontFamily: 'var(--font-sans)', padding: 8, resize: 'vertical', boxSizing: 'border-box',
};
const summaryInput: React.CSSProperties = {
  width: '100%', background: 'var(--surface)', border: '1px solid var(--border-strong)', borderRadius: 8,
  color: 'var(--fg)', fontSize: 12.5, fontFamily: 'var(--font-sans)', padding: '7px 8px', boxSizing: 'border-box',
};
const itemRow: React.CSSProperties = {
  display: 'flex', gap: 8, alignItems: 'flex-start', padding: '10px 0', borderBottom: '1px solid var(--border)',
};
const expandBtn: React.CSSProperties = {
  background: 'none', border: 'none', color: 'var(--fg-muted)', cursor: 'pointer', fontSize: 10.5,
  fontFamily: 'var(--font-mono)', padding: '4px 0 0', letterSpacing: '.04em',
};
const footer: React.CSSProperties = {
  flexShrink: 0, display: 'flex', gap: 8, padding: 14, borderTop: '1px solid var(--border)', background: 'var(--surface-2)',
};
const regenBtn: React.CSSProperties = {
  flex: 1, background: 'var(--accent)', color: 'var(--accent-ink)', border: 'none', borderRadius: 8,
  fontSize: 12.5, fontWeight: 600, padding: '9px', cursor: 'pointer',
};
const primaryWide: React.CSSProperties = {
  width: '100%', background: 'var(--accent)', color: 'var(--accent-ink)', border: 'none', borderRadius: 8,
  fontSize: 12.5, fontWeight: 600, padding: '9px', cursor: 'pointer',
};
const smallPrimary: React.CSSProperties = {
  background: 'var(--accent)', color: 'var(--accent-ink)', border: 'none', borderRadius: 8,
  fontSize: 12, fontWeight: 600, padding: '7px 14px', cursor: 'pointer',
};
const backBtn: React.CSSProperties = {
  background: 'transparent', border: '1px solid var(--border-strong)', borderRadius: 8,
  color: 'var(--fg-dim)', fontSize: 11.5, padding: '5px 10px', cursor: 'pointer',
};
const ticketRow: React.CSSProperties = {
  display: 'block', width: '100%', textAlign: 'left', background: 'var(--surface-2)',
  border: '1px solid var(--border)', borderRadius: 10, padding: '10px 12px', marginBottom: 8, cursor: 'pointer',
};
const ticketKey: React.CSSProperties = {
  fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--accent)', fontWeight: 600, flexShrink: 0,
};
const ticketSummary: React.CSSProperties = { margin: '5px 0 0', fontSize: 12.5, color: 'var(--fg)', lineHeight: 1.4 };
const statusPill: React.CSSProperties = {
  fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '.05em', textTransform: 'uppercase',
  color: 'var(--fg-dim)', border: '1px solid var(--border-strong)', borderRadius: 999, padding: '2px 7px',
};
const resultRow: React.CSSProperties = { display: 'flex', alignItems: 'center', gap: 8, padding: '7px 0', borderBottom: '1px solid var(--border)' };
const resultTag: React.CSSProperties = {
  fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '.06em', color: 'var(--accent)',
  border: '1px solid var(--accent)', borderRadius: 999, padding: '2px 7px', flexShrink: 0,
};
const chipWrap: React.CSSProperties = { display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'center' };
const chip: React.CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: 4, background: 'var(--accent-soft)',
  border: '1px solid var(--accent)', borderRadius: 999, color: 'var(--accent)',
  fontSize: 10.5, fontFamily: 'var(--font-mono)', padding: '2px 8px',
};
const chipX: React.CSSProperties = { background: 'none', border: 'none', color: 'var(--accent)', cursor: 'pointer', fontSize: 12, lineHeight: 1, padding: 0 };
const chipInput: React.CSSProperties = {
  background: 'transparent', border: 'none', outline: 'none', color: 'var(--fg)', fontSize: 11,
  fontFamily: 'var(--font-mono)', minWidth: 70, flex: 1, padding: '2px 0',
};

function toggle(active: boolean): React.CSSProperties {
  return {
    flex: 1, padding: '7px', borderRadius: 8, fontSize: 11.5, cursor: 'pointer',
    fontFamily: 'var(--font-mono)', letterSpacing: '.04em', textTransform: 'capitalize',
    border: `1px solid ${active ? 'var(--accent)' : 'var(--border-strong)'}`,
    background: active ? 'var(--accent-soft)' : 'transparent',
    color: active ? 'var(--accent)' : 'var(--fg-dim)',
  };
}
