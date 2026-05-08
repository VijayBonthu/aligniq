import React from 'react';
import { useNavigate } from 'react-router-dom';
import { text, status as statusTokens } from '../../styles/tokens';
import type { InboxQuestion } from '../../types/overview';

interface Props {
  item: InboxQuestion;
}

export default function InboxRow({ item }: Props) {
  const navigate = useNavigate();
  const isP1 = item.question_type === 'p1_blocker';

  return (
    <button
      type="button"
      onClick={() =>
        navigate(`/dashboard/${item.chat_history_id}?focus=question-${item.question_id}`)
      }
      className="w-full text-left rounded-lg p-3 bg-white/5 hover:bg-white/10 border border-white/10 hover:border-white/20 transition-all duration-150 focus:outline-none focus:ring-2 focus:ring-purple-500/40"
    >
      <div className="flex items-start gap-2 mb-1">
        <span
          className={`px-1.5 py-0.5 rounded text-xs font-bold shrink-0 ${
            isP1 ? statusTokens.danger : statusTokens.warn
          }`}
        >
          {item.question_number}
        </span>
        {item.area_or_category && (
          <span className={`px-1.5 py-0.5 rounded text-xs shrink-0 ${statusTokens.neutral}`}>
            {item.area_or_category}
          </span>
        )}
      </div>
      <p className={`text-sm ${text.primary} line-clamp-2 mb-1`}>
        {item.title || item.question_text}
      </p>
      <p className={`text-xs ${text.dim} truncate`}>{item.project_title}</p>
    </button>
  );
}
