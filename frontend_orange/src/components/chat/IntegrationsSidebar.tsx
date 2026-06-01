import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'react-hot-toast';
import { isAxiosError } from 'axios';
import { listJiraProjects, pushToJira, type JiraProject } from '../../services/chatActionsService';

interface Integration {
  id: string;
  name: string;
  desc: string;
  color: string;
  logo: string;
  live?: boolean; // only Jira write is built; the rest are honestly marked "soon"
}

const INTEGRATIONS: Integration[] = [
  { id: 'jira', name: 'Jira', desc: 'Push risks & sections as an epic + stories', color: '#0052cc', logo: 'J', live: true },
  { id: 'azure', name: 'Azure DevOps', desc: 'Sync work items', color: '#0078d4', logo: 'AZ' },
  { id: 'confluence', name: 'Confluence', desc: 'Publish reports as pages', color: '#172b4d', logo: 'CF' },
  { id: 'github', name: 'GitHub', desc: 'Open issues from risks', color: '#24292e', logo: 'GH' },
  { id: 'slack', name: 'Slack', desc: 'Notify a channel', color: '#4a154b', logo: 'S' },
  { id: 'notion', name: 'Notion', desc: 'Mirror reports', color: '#000', logo: 'N' },
];

export default function IntegrationsSidebar({ chatHistoryId }: { chatHistoryId?: string }) {
  const [jiraOpen, setJiraOpen] = useState(false);

  return (
    <div
      style={{
        width: 252,
        flexShrink: 0,
        borderLeft: '1px solid var(--border)',
        background: 'var(--surface)',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}
    >
      <div style={{ padding: '14px 16px', borderBottom: '1px solid var(--border)', flexShrink: 0 }}>
        <p
          style={{
            fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '.1em',
            textTransform: 'uppercase', color: 'var(--fg-muted)', margin: 0,
          }}
        >
          INTEGRATIONS
        </p>
        <p style={{ fontSize: 11, color: 'var(--fg-dim)', margin: '4px 0 0', lineHeight: 1.4 }}>
          Hand the report off to your delivery tools.
        </p>
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: 12, display: 'flex', flexDirection: 'column', gap: 8 }}>
        {INTEGRATIONS.map((i) => (
          <div
            key={i.id}
            style={{
              padding: '10px 12px', borderRadius: 10, background: 'var(--surface-2)',
              border: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 10,
              opacity: i.live ? 1 : 0.55,
            }}
          >
            <div
              style={{
                width: 28, height: 28, borderRadius: 6, background: `${i.color}24`,
                border: `1px solid ${i.color}55`, color: '#fff', display: 'flex',
                alignItems: 'center', justifyContent: 'center', fontFamily: 'var(--font-mono)',
                fontSize: 10, fontWeight: 700,
              }}
            >
              {i.logo}
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <p style={{ fontSize: 12, color: 'var(--fg)', fontWeight: 500, margin: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {i.name}
              </p>
              <p style={{ fontSize: 10.5, color: 'var(--fg-muted)', margin: '2px 0 0', lineHeight: 1.3 }}>
                {i.desc}
              </p>
            </div>
            {i.live ? (
              <button
                onClick={() => setJiraOpen(true)}
                disabled={!chatHistoryId}
                style={{
                  padding: '5px 10px', fontSize: 11, fontFamily: 'var(--font-mono)', letterSpacing: '.06em',
                  background: 'var(--accent-soft)', border: '1px solid var(--accent)', borderRadius: 999,
                  color: 'var(--accent)', cursor: chatHistoryId ? 'pointer' : 'not-allowed',
                }}
              >
                PUSH
              </button>
            ) : (
              <span
                style={{
                  padding: '4px 8px', fontSize: 9, fontFamily: 'var(--font-mono)', letterSpacing: '.06em',
                  background: 'transparent', border: '1px solid var(--border)', borderRadius: 999, color: 'var(--fg-muted)',
                }}
              >
                SOON
              </span>
            )}
          </div>
        ))}
      </div>
      {jiraOpen && chatHistoryId && (
        <JiraPushModal chatHistoryId={chatHistoryId} onClose={() => setJiraOpen(false)} />
      )}
    </div>
  );
}

function JiraPushModal({ chatHistoryId, onClose }: { chatHistoryId: string; onClose: () => void }) {
  const navigate = useNavigate();
  const [projects, setProjects] = useState<JiraProject[] | null>(null);
  const [notConnected, setNotConnected] = useState(false);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [projectKey, setProjectKey] = useState('');
  const [scope, setScope] = useState<'risks' | 'sections'>('risks');

  const loadProjects = useCallback(async () => {
    setLoading(true);
    try {
      const ps = await listJiraProjects();
      setProjects(ps);
      if (ps.length) setProjectKey(ps[0].key);
    } catch (err) {
      if (isAxiosError(err) && err.response?.status === 401) setNotConnected(true);
      else toast.error('Could not load Jira projects');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadProjects();
  }, [loadProjects]);

  const push = async () => {
    if (!projectKey) return;
    setBusy(true);
    try {
      const res = await pushToJira(chatHistoryId, { project_key: projectKey, scope });
      toast.success(`Created ${res.epic_key} + ${res.issue_keys.length} stories in Jira`);
      onClose();
    } catch (err) {
      const detail =
        (isAxiosError(err) && (err.response?.data as { detail?: string })?.detail) ||
        'Jira push failed';
      toast.error(detail);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={modalOverlay} onClick={onClose}>
      <div style={modal} onClick={(e) => e.stopPropagation()}>
        <p style={modalTitle}>Push to Jira</p>
        {loading ? (
          <p style={{ fontSize: 12, color: 'var(--fg-muted)' }}>Loading projects…</p>
        ) : notConnected ? (
          <>
            <p style={{ fontSize: 12, color: 'var(--fg-dim)', lineHeight: 1.5 }}>
              Jira isn't connected. Connect it in Settings, then come back to push.
            </p>
            <button onClick={() => navigate('/settings')} style={primaryBtn}>Connect Jira</button>
          </>
        ) : (
          <>
            <label style={label}>Project</label>
            <select value={projectKey} onChange={(e) => setProjectKey(e.target.value)} style={modalSelect}>
              {(projects || []).map((p) => <option key={p.key} value={p.key}>{p.name} ({p.key})</option>)}
            </select>
            <label style={label}>What to push</label>
            <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
              {(['risks', 'sections'] as const).map((s) => (
                <button
                  key={s}
                  onClick={() => setScope(s)}
                  style={{
                    flex: 1, padding: '7px', borderRadius: 8, fontSize: 11.5, cursor: 'pointer',
                    fontFamily: 'var(--font-mono)', letterSpacing: '.04em', textTransform: 'capitalize',
                    border: `1px solid ${scope === s ? 'var(--accent)' : 'var(--border-strong)'}`,
                    background: scope === s ? 'var(--accent-soft)' : 'transparent',
                    color: scope === s ? 'var(--accent)' : 'var(--fg-dim)',
                  }}
                >
                  {s}
                </button>
              ))}
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button onClick={onClose} style={ghostBtn}>Cancel</button>
              <button onClick={push} disabled={busy || !projectKey} style={primaryBtn}>
                {busy ? 'Pushing…' : 'Create epic + stories'}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

const modalOverlay: React.CSSProperties = {
  position: 'fixed', inset: 0, background: 'rgba(0,0,0,.45)', zIndex: 70,
  display: 'flex', alignItems: 'center', justifyContent: 'center',
};
const modal: React.CSSProperties = {
  width: 340, maxWidth: '90vw', background: 'var(--surface)', border: '1px solid var(--border-strong)',
  borderRadius: 12, padding: 18,
};
const modalTitle: React.CSSProperties = { margin: '0 0 12px', fontSize: 14, fontWeight: 600, color: 'var(--fg)' };
const label: React.CSSProperties = { display: 'block', fontFamily: 'var(--font-mono)', fontSize: 9.5, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--fg-muted)', margin: '4px 0 4px' };
const modalSelect: React.CSSProperties = { width: '100%', boxSizing: 'border-box', background: 'var(--surface-2)', border: '1px solid var(--border-strong)', borderRadius: 8, color: 'var(--fg)', fontSize: 12.5, padding: '8px', marginBottom: 6 };
const primaryBtn: React.CSSProperties = { flex: 1, background: 'var(--accent)', color: '#1a0a04', border: 'none', borderRadius: 8, fontSize: 12.5, fontWeight: 600, padding: '9px', cursor: 'pointer' };
const ghostBtn: React.CSSProperties = { flex: 1, background: 'transparent', border: '1px solid var(--border-strong)', borderRadius: 8, color: 'var(--fg-dim)', fontSize: 12.5, padding: '9px', cursor: 'pointer' };
