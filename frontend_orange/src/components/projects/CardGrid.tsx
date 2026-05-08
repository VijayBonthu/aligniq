import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import ProjectCard, { readinessToStatus } from './ProjectCard';
import NewProjectCard from './NewProjectCard';
import type { ProjectRow } from '../../types/overview';

type Filter = 'all' | 'active' | 'analyzing' | 'complete';

const FILTERS: Filter[] = ['all', 'active', 'analyzing', 'complete'];

interface Props {
  projects: ProjectRow[];
}

export default function CardGrid({ projects }: Props) {
  const navigate = useNavigate();
  const [filter, setFilter] = useState<Filter>('all');

  const filtered = useMemo(() => {
    if (filter === 'all') return projects;
    return projects.filter((p) => readinessToStatus(p.readiness.status) === filter);
  }, [projects, filter]);

  return (
    <div
      style={{
        flex: 1,
        overflowY: 'auto',
        padding: '26px 30px',
        animation: 'fadeIn .25s ease',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          marginBottom: 24,
          gap: 16,
        }}
      >
        <div>
          <p
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 10,
              letterSpacing: '.14em',
              textTransform: 'uppercase',
              color: 'var(--fg-muted)',
              marginBottom: 5,
            }}
          >
            PROJECTS · {projects.length} TOTAL
          </p>
          <h1
            style={{
              fontFamily: 'var(--font-display)',
              fontSize: 26,
              fontWeight: 400,
              letterSpacing: '-.02em',
              color: 'var(--fg)',
              margin: 0,
            }}
          >
            Your scopes
          </h1>
        </div>
        <button
          type="button"
          onClick={() => navigate('/new-project')}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 7,
            padding: '9px 16px',
            borderRadius: 999,
            fontSize: 13,
            fontWeight: 500,
            background: 'var(--accent)',
            color: '#1a0a04',
            border: 'none',
            boxShadow: 'var(--glow)',
            cursor: 'pointer',
            fontFamily: 'var(--font-sans)',
          }}
        >
          <svg width="12" height="12" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path d="M12 5v14M5 12h14" strokeWidth="2.5" strokeLinecap="round" />
          </svg>
          New project
        </button>
      </div>
      <div
        style={{
          display: 'flex',
          gap: 2,
          marginBottom: 22,
          borderBottom: '1px solid var(--border)',
        }}
      >
        {FILTERS.map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            style={{
              padding: '7px 13px',
              background: 'none',
              border: 'none',
              borderBottom: `2px solid ${filter === f ? 'var(--accent)' : 'transparent'}`,
              color: filter === f ? 'var(--accent)' : 'var(--fg-dim)',
              fontSize: 13,
              fontWeight: 500,
              cursor: 'pointer',
              transition: 'all .15s',
              marginBottom: -1,
              fontFamily: 'var(--font-sans)',
            }}
          >
            {f.charAt(0).toUpperCase() + f.slice(1)}
          </button>
        ))}
      </div>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
          gap: 14,
        }}
      >
        {filtered.map((p, i) => (
          <ProjectCard key={p.chat_history_id} project={p} delay={i * 40} />
        ))}
        <NewProjectCard />
      </div>
    </div>
  );
}
