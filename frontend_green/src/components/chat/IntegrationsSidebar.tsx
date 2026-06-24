import { useState } from 'react';
import JiraWorkspace from './JiraWorkspace';

interface Integration {
  id: string;
  name: string;
  desc: string;
  color: string;
  logo: string;
  live?: boolean; // only Jira write is built; the rest are honestly marked "soon"
}

const INTEGRATIONS: Integration[] = [
  { id: 'jira', name: 'Jira', desc: 'Push, tag & manage epics + stories', color: '#0052cc', logo: 'J', live: true },
  { id: 'azure', name: 'Azure DevOps', desc: 'Sync work items', color: '#0078d4', logo: 'AZ' },
  { id: 'confluence', name: 'Confluence', desc: 'Publish reports as pages', color: '#172b4d', logo: 'CF' },
  { id: 'github', name: 'GitHub', desc: 'Open issues from risks', color: '#24292e', logo: 'GH' },
  { id: 'slack', name: 'Slack', desc: 'Notify a channel', color: '#4a154b', logo: 'S' },
  { id: 'notion', name: 'Notion', desc: 'Mirror reports', color: '#000', logo: 'N' },
];

interface SidebarProps {
  chatHistoryId?: string;
  /** Whether the panel is shown at all (collapsed → nothing on desktop / closed drawer on mobile). */
  open: boolean;
  onClose: () => void;
  /** Mobile/tablet: render as an off-canvas drawer over the content instead of an inline rail. */
  overlay: boolean;
}

export default function IntegrationsSidebar({ chatHistoryId, open, onClose, overlay }: SidebarProps) {
  const [jiraOpen, setJiraOpen] = useState(false);

  if (!open) return null;

  const inner = (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden', background: 'var(--surface)' }}>
      <div
        style={{
          padding: '13px 14px 13px 16px',
          borderBottom: '1px solid var(--border)',
          flexShrink: 0,
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          gap: 8,
        }}
      >
        <div style={{ minWidth: 0 }}>
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
        <button
          onClick={onClose}
          aria-label={overlay ? 'Close integrations' : 'Collapse integrations'}
          title={overlay ? 'Close' : 'Collapse'}
          style={{
            flexShrink: 0,
            width: 28,
            height: 28,
            borderRadius: 7,
            border: '1px solid var(--border)',
            background: 'transparent',
            color: 'var(--fg-muted)',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            {overlay ? (
              <path d="M18 6L6 18M6 6l12 12" strokeWidth="2" strokeLinecap="round" />
            ) : (
              <path d="M9 6l6 6-6 6" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            )}
          </svg>
        </button>
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
                OPEN
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
    </div>
  );

  const workspace = jiraOpen && chatHistoryId ? (
    <JiraWorkspace chatHistoryId={chatHistoryId} onClose={() => setJiraOpen(false)} />
  ) : null;

  if (overlay) {
    return (
      <>
        <div
          onClick={onClose}
          style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.45)', zIndex: 55 }}
        />
        <aside
          style={{
            position: 'fixed',
            top: 0,
            right: 0,
            bottom: 0,
            width: 300,
            maxWidth: '86vw',
            zIndex: 56,
            borderLeft: '1px solid var(--border-strong)',
            boxShadow: 'var(--shadow-lg)',
            animation: 'slideInRight .2s ease',
          }}
        >
          {inner}
        </aside>
        {workspace}
      </>
    );
  }

  return (
    <aside style={{ width: 252, flexShrink: 0, borderLeft: '1px solid var(--border)' }}>
      {inner}
      {workspace}
    </aside>
  );
}
