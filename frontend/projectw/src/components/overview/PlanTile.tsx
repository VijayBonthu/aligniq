import React from 'react';
import { Link } from 'react-router-dom';
import KpiTile from './KpiTile';
import { text } from '../../styles/tokens';
import type { SubscriptionBlock } from '../../types/overview';

interface Props {
  subscription: SubscriptionBlock | null;
}

const tierLabel: Record<string, string> = {
  free: 'Free',
  basic: 'Basic',
  plus: 'Plus',
  pro: 'Pro',
};

export default function PlanTile({ subscription }: Props) {
  if (!subscription) {
    return (
      <KpiTile label="Plan" accentBar="bg-gradient-to-r from-purple-500 to-pink-500">
        <div className={`text-3xl md:text-4xl font-bold ${text.primary}`}>—</div>
      </KpiTile>
    );
  }

  const { tier, usage, limits } = subscription;
  const chatsUsed = usage.chats;
  const chatsLimit = limits.max_chats;
  const regenUsed = usage.report_regenerations_used;
  const regenLimit = limits.monthly_report_regen;

  const chatPct = chatsLimit && chatsLimit > 0 ? Math.min(100, (chatsUsed / chatsLimit) * 100) : 0;
  const chatBar = chatPct >= 100 ? 'bg-red-500' : chatPct >= 80 ? 'bg-yellow-500' : 'bg-indigo-500';

  return (
    <KpiTile
      label="Plan"
      accentBar="bg-gradient-to-r from-purple-500 to-pink-500"
      icon={
        <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
        </svg>
      }
      sublabel={
        <div className="flex items-center justify-between gap-2">
          <span>
            Regen {regenUsed}
            {regenLimit !== null ? `/${regenLimit}` : ''}
          </span>
          {tier !== 'pro' && (
            <Link to="/pricing" className="text-xs text-purple-300 hover:text-purple-200 underline">
              Upgrade
            </Link>
          )}
        </div>
      }
    >
      <div className="flex items-baseline gap-2">
        <span className={`text-3xl md:text-4xl font-bold ${text.primary}`}>{tierLabel[tier] || tier}</span>
      </div>
      <div className={`mt-1 text-xs ${text.muted}`}>
        Chats {chatsUsed}
        {chatsLimit !== null ? `/${chatsLimit}` : ''}
      </div>
      {chatsLimit !== null && (
        <div className="mt-2 w-full bg-white/10 rounded-full h-2 overflow-hidden">
          <div className={`h-full transition-all duration-500 ${chatBar}`} style={{ width: `${chatPct}%` }} />
        </div>
      )}
    </KpiTile>
  );
}
