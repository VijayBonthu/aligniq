import React from 'react';

interface UsageCounterProps {
  label: string;
  current: number;
  limit: number | null;
}

export default function UsageCounter({ label, current, limit }: UsageCounterProps) {
  if (limit === null) return null;

  const pct = limit > 0 ? current / limit : 0;
  const colorClass =
    pct >= 1 ? 'bg-red-500/20 text-red-400 border-red-500/30' :
    pct >= 0.8 ? 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30' :
    'bg-indigo-500/20 text-indigo-300 border-indigo-500/30';

  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border ${colorClass}`}>
      {label}: {current}/{limit}
    </span>
  );
}
