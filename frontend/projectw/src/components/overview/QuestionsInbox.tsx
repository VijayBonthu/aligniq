import React, { useMemo } from 'react';
import InboxRow from './InboxRow';
import { surface, text } from '../../styles/tokens';
import type { InboxQuestion } from '../../types/overview';

interface Props {
  inbox: InboxQuestion[];
}

export default function QuestionsInbox({ inbox }: Props) {
  const { p1, kickstart } = useMemo(() => {
    const p1List: InboxQuestion[] = [];
    const kickList: InboxQuestion[] = [];
    for (const q of inbox) {
      if (q.question_type === 'p1_blocker') p1List.push(q);
      else kickList.push(q);
    }
    return { p1: p1List, kickstart: kickList };
  }, [inbox]);

  return (
    <div className={`rounded-xl ${surface.card} flex flex-col max-h-[calc(100vh-14rem)]`}>
      <div className={`px-4 py-3 ${surface.header} rounded-t-xl flex items-center justify-between`}>
        <div>
          <h2 className={`text-sm font-semibold ${text.primary}`}>Questions Inbox</h2>
          <p className={`text-xs ${text.muted}`}>Unanswered across all projects</p>
        </div>
        <span className="px-2 py-0.5 rounded-full bg-white/10 text-xs text-gray-300">
          {inbox.length}
        </span>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-4">
        {inbox.length === 0 ? (
          <div className="text-center py-10">
            <div className="h-12 w-12 mx-auto mb-2 rounded-full bg-green-500/10 border border-green-500/20 flex items-center justify-center">
              <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6 text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <p className={`text-sm ${text.primary}`}>Inbox zero</p>
            <p className={`text-xs ${text.muted}`}>No unanswered questions.</p>
          </div>
        ) : (
          <>
            {p1.length > 0 && (
              <div>
                <h3 className={`text-xs font-semibold text-red-400 uppercase tracking-wide mb-2`}>
                  P1 Blockers ({p1.length})
                </h3>
                <div className="space-y-2">
                  {p1.map(q => (
                    <InboxRow key={q.question_id} item={q} />
                  ))}
                </div>
              </div>
            )}
            {kickstart.length > 0 && (
              <div>
                <h3 className={`text-xs font-semibold text-yellow-400 uppercase tracking-wide mb-2`}>
                  Kickstart ({kickstart.length})
                </h3>
                <div className="space-y-2">
                  {kickstart.map(q => (
                    <InboxRow key={q.question_id} item={q} />
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
