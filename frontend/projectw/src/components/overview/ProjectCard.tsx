import React from 'react';
import { useNavigate } from 'react-router-dom';
import { surface, text, status as statusTokens, readinessColor, readinessBar } from '../../styles/tokens';
import type { ProjectRow } from '../../types/overview';

interface Props {
  project: ProjectRow;
}

function timeAgo(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  const diff = Date.now() - d.getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days < 7) return `${days}d ago`;
  return d.toLocaleDateString();
}

export default function ProjectCard({ project }: Props) {
  const navigate = useNavigate();
  const score = project.readiness.score;
  const scorePct = Math.round(score * 100);

  const p1Pending = project.questions_summary.p1_total - project.questions_summary.p1_answered;
  const kickPending =
    project.questions_summary.kickstart_total - project.questions_summary.kickstart_answered;

  return (
    <button
      type="button"
      onClick={() => navigate(`/dashboard/${project.chat_history_id}`)}
      className={`text-left w-full rounded-xl p-4 md:p-5 transition-all duration-200 ${surface.card} ${surface.cardHover} focus:outline-none focus:ring-2 focus:ring-purple-500/40`}
    >
      {/* Header: title + mode badge */}
      <div className="flex items-start justify-between gap-3 mb-3">
        <h3 className={`text-base md:text-lg font-semibold ${text.primary} truncate`}>
          {project.title}
        </h3>
        <span
          className={`shrink-0 px-2 py-0.5 rounded-full text-xs font-medium ${
            project.analysis_mode === 'presales'
              ? 'bg-purple-500/20 text-purple-300 border border-purple-500/30'
              : 'bg-blue-500/20 text-blue-300 border border-blue-500/30'
          }`}
        >
          {project.analysis_mode === 'presales' ? 'Pre-Sales' : 'Full Report'}
        </span>
      </div>

      {/* Message preview */}
      {project.last_message_preview && (
        <p className={`text-xs ${text.muted} line-clamp-2 mb-3`}>
          {project.last_message_preview}
        </p>
      )}

      {/* Readiness bar */}
      {project.readiness.status !== 'not_analyzed' && (
        <div className="mb-3">
          <div className="flex items-center justify-between mb-1">
            <span className={`text-xs ${text.muted}`}>Readiness</span>
            <span className={`text-xs font-semibold ${readinessColor(score)}`}>{scorePct}%</span>
          </div>
          <div className="w-full bg-white/10 rounded-full h-1.5 overflow-hidden">
            <div
              className={`h-full transition-all duration-500 ${readinessBar(score)}`}
              style={{ width: `${scorePct}%` }}
            />
          </div>
        </div>
      )}

      {/* Chips row */}
      <div className="flex flex-wrap items-center gap-1.5">
        {p1Pending > 0 && (
          <span className={`px-2 py-0.5 rounded text-xs ${statusTokens.danger}`}>
            {p1Pending} P1 pending
          </span>
        )}
        {kickPending > 0 && (
          <span className={`px-2 py-0.5 rounded text-xs ${statusTokens.warn}`}>
            {kickPending} Q pending
          </span>
        )}
        {project.questions_summary.vague_count > 0 && (
          <span className={`px-2 py-0.5 rounded text-xs ${statusTokens.warn}`}>
            {project.questions_summary.vague_count} vague
          </span>
        )}
        {project.pending_changes.total > 0 && (
          <span
            className={`px-2 py-0.5 rounded text-xs ${
              project.pending_changes.has_conflicts ? statusTokens.warn : statusTokens.info
            }`}
          >
            {project.pending_changes.total} pending change{project.pending_changes.total !== 1 ? 's' : ''}
          </span>
        )}
        {project.report_versions > 1 && (
          <span className={`px-2 py-0.5 rounded text-xs ${statusTokens.neutral}`}>
            v{project.report_versions}
          </span>
        )}
      </div>

      {/* Footer */}
      <div className={`mt-3 text-xs ${text.dim} flex justify-between items-center`}>
        <span>Updated {timeAgo(project.modified_at)}</span>
      </div>
    </button>
  );
}
