import { useEffect, useState } from 'react';
import { fetchOverview } from '../services/projectsService';
import type { OverviewResponse } from '../types/overview';
import CardGrid from '../components/projects/CardGrid';
import QuestionsInbox from '../components/projects/QuestionsInbox';
import KpiStrip from '../components/projects/KpiStrip';

export default function ProjectsPage() {
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

  return (
    <div style={{ flex: 1, display: 'flex', overflow: 'hidden', minHeight: 0 }}>
      <div
        style={{
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          minWidth: 0,
        }}
      >
        <div style={{ paddingTop: 26 }}>
          <KpiStrip kpis={overview.kpis} subscription={overview.subscription} />
        </div>
        <CardGrid projects={overview.projects} />
      </div>
      <QuestionsInbox inbox={overview.questions_inbox} />
    </div>
  );
}
