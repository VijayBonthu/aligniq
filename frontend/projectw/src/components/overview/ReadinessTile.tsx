import React from 'react';
import KpiTile from './KpiTile';
import { text, readinessColor, readinessBar } from '../../styles/tokens';

interface Props {
  avgReadiness: number;
  trend7d: number;
}

export default function ReadinessTile({ avgReadiness, trend7d }: Props) {
  const pct = Math.round(avgReadiness * 100);
  const trendPct = Math.round(trend7d * 100);
  const trendPositive = trendPct > 0;
  const trendNeutral = trendPct === 0;

  return (
    <KpiTile
      label="Avg. Readiness"
      accentBar="bg-gradient-to-r from-green-500 via-yellow-500 to-red-500"
      icon={
        <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19V6l12-3v13M9 19a3 3 0 11-6 0 3 3 0 016 0zm12-3a3 3 0 11-6 0 3 3 0 016 0z" />
        </svg>
      }
      sublabel={
        trendNeutral ? (
          <span className={text.muted}>No change vs. last 7d</span>
        ) : (
          <span className={trendPositive ? 'text-green-400' : 'text-red-400'}>
            {trendPositive ? '▲' : '▼'} {Math.abs(trendPct)}% vs. older projects
          </span>
        )
      }
    >
      <div className="flex items-baseline gap-2">
        <span className={`text-3xl md:text-4xl font-bold ${readinessColor(avgReadiness)}`}>{pct}%</span>
      </div>
      <div className="mt-2 w-full bg-white/10 rounded-full h-2 overflow-hidden">
        <div
          className={`h-full transition-all duration-500 ${readinessBar(avgReadiness)}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </KpiTile>
  );
}
