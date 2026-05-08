import React from 'react';
import KpiTile from './KpiTile';
import { text } from '../../styles/tokens';

interface Props {
  total: number;
  presales: number;
  full: number;
}

export default function TotalProjectsTile({ total, presales, full }: Props) {
  return (
    <KpiTile
      label="Projects"
      accentBar="bg-gradient-to-r from-blue-500 to-indigo-500"
      icon={
        <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7h18M3 12h18M3 17h18" />
        </svg>
      }
      sublabel={
        <span className="flex gap-3">
          <span><span className="text-purple-300 font-semibold">{presales}</span> presales</span>
          <span><span className="text-blue-300 font-semibold">{full}</span> full report</span>
        </span>
      }
    >
      <div className={`text-3xl md:text-4xl font-bold ${text.primary}`}>{total}</div>
    </KpiTile>
  );
}
