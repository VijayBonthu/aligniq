import React from 'react';
import { useNavigate } from 'react-router-dom';
import { text } from '../../styles/tokens';

export default function NewProjectCard() {
  const navigate = useNavigate();
  return (
    <button
      type="button"
      onClick={() => navigate('/dashboard')}
      className="w-full min-h-[140px] rounded-xl border-2 border-dashed border-white/15 hover:border-purple-400/60 hover:bg-white/5 transition-all duration-200 flex flex-col items-center justify-center gap-2 p-4 focus:outline-none focus:ring-2 focus:ring-purple-500/40"
    >
      <div className="h-10 w-10 rounded-full bg-gradient-to-br from-blue-500/20 to-purple-500/20 border border-white/10 flex items-center justify-center">
        <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 text-purple-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
        </svg>
      </div>
      <span className={`text-sm font-medium ${text.primary}`}>New Project</span>
      <span className={`text-xs ${text.muted}`}>Upload a document to get started</span>
    </button>
  );
}
