import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchOverview } from '../services/projectsService';
import type { OverviewResponse } from '../types/overview';
import CardGrid from '../components/projects/CardGrid';
import KpiStrip from '../components/projects/KpiStrip';

export default function ProjectsPage() {
  const navigate = useNavigate();
  const [overview, setOverview] = useState<OverviewResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const ov = await fetchOverview();
        if (!cancelled) setOverview(ov);
      } catch (e) {
        console.error('Failed to load overview', e);
        if (!cancelled) setError('Failed to load projects overview.');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // The inbox's one real job — "which engagements need me" — folds into a KPI
  // tile + a grid filter, so we surface it without a redundant 320px rail.
  const attention = useMemo(() => {
    let count = 0;
    let blockers = 0;
    for (const p of overview?.projects ?? []) {
      const open = Math.max(0, p.questions_summary.p1_total - p.questions_summary.p1_answered);
      if (open > 0 || p.pending_changes.has_conflicts || p.readiness.status === 'needs_more_info') {
        count += 1;
      }
      blockers += open;
    }
    return { count, blockers };
  }, [overview]);

  if (loading) {
    return (
      <div
        style={{
          flex: 1,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: 'var(--fg-muted)',
        }}
      >
        <div
          style={{
            width: 28,
            height: 28,
            border: '2px solid var(--border-strong)',
            borderTopColor: 'var(--accent)',
            borderRadius: '50%',
            animation: 'spin 1s linear infinite',
          }}
        />
      </div>
    );
  }

  if (error || !overview) {
    return (
      <div
        style={{
          flex: 1,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: 40,
        }}
      >
        <div
          style={{
            padding: '16px 22px',
            background: 'color-mix(in oklab, var(--danger) 10%, transparent)',
            border: '1px solid color-mix(in oklab, var(--danger) 30%, transparent)',
            borderRadius: 'var(--radius)',
            color: 'var(--danger)',
            fontSize: 13,
          }}
        >
          {error || 'No overview data.'}
        </div>
      </div>
    );
  }

  const projectCount = overview.projects.length;

  return (
    <div
      style={{
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
        minHeight: 0,
      }}
    >
      <header
        style={{
          display: 'flex',
          alignItems: 'flex-end',
          justifyContent: 'space-between',
          gap: 16,
          padding: 'clamp(18px, 4vw, 26px) clamp(16px, 4vw, 30px) 0',
          flexWrap: 'wrap',
          animation: 'fadeIn .25s ease',
        }}
      >
        <div>
          <p className="label-mono" style={{ margin: '0 0 6px' }}>
            Workspace · {projectCount} {projectCount === 1 ? 'engagement' : 'engagements'}
          </p>
          <h1
            style={{
              fontFamily: 'var(--font-display)',
              fontSize: 'clamp(24px, 5vw, 30px)',
              fontWeight: 400,
              letterSpacing: '-.02em',
              color: 'var(--fg)',
              margin: 0,
            }}
          >
            Projects
          </h1>
        </div>
        <button
          type="button"
          onClick={() => navigate('/new-project')}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 7,
            padding: '10px 17px',
            borderRadius: 999,
            fontSize: 13,
            fontWeight: 500,
            background: 'var(--accent)',
            color: 'var(--accent-ink)',
            border: 'none',
            boxShadow: 'var(--glow)',
            cursor: 'pointer',
            fontFamily: 'var(--font-sans)',
            whiteSpace: 'nowrap',
          }}
        >
          <svg width="13" height="13" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path d="M12 5v14M5 12h14" strokeWidth="2.5" strokeLinecap="round" />
          </svg>
          New project
        </button>
      </header>

      <div style={{ paddingTop: 14 }}>
        <KpiStrip kpis={overview.kpis} subscription={overview.subscription} attention={attention} />
      </div>

      <CardGrid projects={overview.projects} />
    </div>
  );
}
