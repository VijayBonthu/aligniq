import { useNavigate } from 'react-router-dom';

interface Integration {
  id: string;
  name: string;
  desc: string;
  color: string;
  logo: string;
}

const INTEGRATIONS: Integration[] = [
  { id: 'jira', name: 'Jira', desc: 'Push risks, pull tickets', color: '#0052cc', logo: 'J' },
  { id: 'azure', name: 'Azure DevOps', desc: 'Sync work items', color: '#0078d4', logo: 'AZ' },
  { id: 'confluence', name: 'Confluence', desc: 'Publish reports as pages', color: '#172b4d', logo: 'CF' },
  { id: 'github', name: 'GitHub', desc: 'Open issues from risks', color: '#24292e', logo: 'GH' },
  { id: 'slack', name: 'Slack', desc: 'Notify a channel', color: '#4a154b', logo: 'S' },
  { id: 'notion', name: 'Notion', desc: 'Mirror reports', color: '#000', logo: 'N' },
];

export default function IntegrationsSidebar() {
  const navigate = useNavigate();
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
      <div
        style={{
          padding: '14px 16px',
          borderBottom: '1px solid var(--border)',
          flexShrink: 0,
        }}
      >
        <p
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 10,
            letterSpacing: '.1em',
            textTransform: 'uppercase',
            color: 'var(--fg-muted)',
            margin: 0,
          }}
        >
          INTEGRATIONS
        </p>
        <p
          style={{
            fontSize: 11,
            color: 'var(--fg-dim)',
            margin: '4px 0 0',
            lineHeight: 1.4,
          }}
        >
          Wire AlignIQ into the tools your team already uses.
        </p>
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: 12, display: 'flex', flexDirection: 'column', gap: 8 }}>
        {INTEGRATIONS.map((i) => (
          <div
            key={i.id}
            style={{
              padding: '10px 12px',
              borderRadius: 10,
              background: 'var(--surface-2)',
              border: '1px solid var(--border)',
              display: 'flex',
              alignItems: 'center',
              gap: 10,
            }}
          >
            <div
              style={{
                width: 28,
                height: 28,
                borderRadius: 6,
                background: `${i.color}24`,
                border: `1px solid ${i.color}55`,
                color: '#fff',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontFamily: 'var(--font-mono)',
                fontSize: 10,
                fontWeight: 700,
              }}
            >
              {i.logo}
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <p
                style={{
                  fontSize: 12,
                  color: 'var(--fg)',
                  fontWeight: 500,
                  margin: 0,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
              >
                {i.name}
              </p>
              <p
                style={{
                  fontSize: 10.5,
                  color: 'var(--fg-muted)',
                  margin: '2px 0 0',
                  lineHeight: 1.3,
                }}
              >
                {i.desc}
              </p>
            </div>
            <button
              onClick={() => navigate('/settings')}
              style={{
                padding: '5px 10px',
                fontSize: 11,
                fontFamily: 'var(--font-mono)',
                letterSpacing: '.06em',
                background: 'transparent',
                border: '1px solid var(--border-strong)',
                borderRadius: 999,
                color: 'var(--fg-dim)',
                cursor: 'pointer',
              }}
            >
              CONNECT
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
