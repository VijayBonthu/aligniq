import React from 'react';
import { surface, text } from '../../styles/tokens';

interface KpiTileProps {
  label: string;
  children: React.ReactNode;
  sublabel?: React.ReactNode;
  icon?: React.ReactNode;
  accentBar?: string;
  className?: string;
}

export default function KpiTile({
  label,
  children,
  sublabel,
  icon,
  accentBar = 'bg-gradient-to-r from-blue-500 to-purple-500',
  className = '',
}: KpiTileProps) {
  return (
    <div className={`relative overflow-hidden rounded-xl p-4 md:p-5 ${surface.card} ${className}`}>
      <div className={`absolute top-0 left-0 right-0 h-0.5 ${accentBar}`} />
      <div className="flex items-start justify-between mb-2">
        <span className={`text-xs uppercase tracking-wide ${text.muted}`}>{label}</span>
        {icon && <div className={text.muted}>{icon}</div>}
      </div>
      <div className="mt-1">{children}</div>
      {sublabel && <div className={`mt-2 text-xs ${text.muted}`}>{sublabel}</div>}
    </div>
  );
}
