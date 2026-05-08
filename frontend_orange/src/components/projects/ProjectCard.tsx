import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import ScoreRing from '../ui/ScoreRing';
import StatusDot, { type StatusKind } from '../ui/StatusDot';
import { Tag } from '../ui/Chips';
import type { ProjectRow, ReadinessStatus } from '../../types/overview';

interface Props {
  project: ProjectRow;
  delay?: number;
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

export function readinessToStatus(r: ReadinessStatus): StatusKind {
  switch (r) {
    case 'ready':
      return 'complete';
    case 'ready_with_assumptions':
      return 'active';
    case 'needs_more_info':
      return 'analyzing';
    default:
      return 'unknown';
  }
}

function Stat({ icon, val, color }: { icon: 'msg' | 'warn' | 'q'; val: number; color?: string }) {
  const icons: Record<string, React.ReactNode> = {
    msg: (
      <svg width="11" height="11" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" strokeWidth="1.8" />
      </svg>
    ),
    warn: (
      <svg width="11" height="11" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path
          d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0zM12 9v4M12 17h.01"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    ),
    q: (
      <svg width="11" height="11" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <circle cx="12" cy="12" r="10" strokeWidth="1.8" />
        <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3M12 17h.01" strokeWidth="1.8" strokeLinecap="round" />
      </svg>
    ),
  };
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 4,
        fontFamily: 'var(--font-mono)',
        fontSize: 11,
        color: color || 'var(--fg-dim)',
      }}
    >
      {icons[icon]}
      {val}
    </span>
  );
}

export default function ProjectCard({ project, delay = 0 }: Props) {
  const navigate = useNavigate();
  const [hov, setHov] = useState(false);

  const scorePct = Math.round(project.readiness.score * 100);
  const isPipelineLive =
    project.pipeline_status === 'running' || project.pipeline_status === 'queued';
  const status: StatusKind = isPipelineLive
    ? 'analyzing'
    : readinessToStatus(project.readiness.status);
  const p1Pending = project.questions_summary.p1_total - project.questions_summary.p1_answered;
  const kickPending =
    project.questions_summary.kickstart_total - project.questions_summary.kickstart_answered;
  const risks = p1Pending;
  const questions = kickPending;

  const modeTag = project.analysis_mode === 'presales' ? 'PRE-SALES' : 'FULL REPORT';

  return (
    <div
      onClick={() => {
        const ps = project.pipeline_status;
        const isPipelineLive = ps === 'running' || ps === 'queued';
        const dest = isPipelineLive
          ? `/full-pipeline/${project.chat_history_id}`
          : project.full_report_generated && project.chat_history_id
          ? `/chat/${project.chat_history_id}`
          : `/new-project/${project.chat_history_id}`;
        navigate(dest);
      }}
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      style={{
        background: hov ? 'var(--surface-2)' : 'var(--surface)',
        border: `1px solid ${hov ? 'var(--border-strong)' : 'var(--border)'}`,
        borderRadius: 'var(--radius-lg)',
        padding: '20px 22px',
        cursor: 'pointer',
        transition: 'all .18s ease',
        transform: hov ? 'translateY(-2px)' : 'none',
        boxShadow: hov ? '0 8px 32px -8px rgba(0,0,0,.4)' : 'none',
        animation: `fadeUp .3s ${delay}ms ease both`,
        position: 'relative',
        overflow: 'hidden',
      }}
    >
      {status === 'active' && (
        <div
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            height: 2,
            background: 'linear-gradient(90deg, var(--accent), var(--accent-2))',
            borderRadius: '18px 18px 0 0',
          }}
        />
      )}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          marginBottom: 10,
        }}
      >
        <div style={{ flex: 1, minWidth: 0 }}>
          <p
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 9,
              letterSpacing: '.1em',
              textTransform: 'uppercase',
              color: 'var(--fg-muted)',
              marginBottom: 3,
            }}
          >
            {modeTag}
          </p>
          <h3
            style={{
              fontSize: 14.5,
              fontWeight: 600,
              color: 'var(--fg)',
              lineHeight: 1.3,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
              margin: 0,
            }}
          >
            {project.title}
          </h3>
        </div>
        <ScoreRing score={scorePct} size={38} />
      </div>
      {project.last_message_preview && (
        <p
          style={{
            fontSize: 12,
            color: 'var(--fg-muted)',
            lineHeight: 1.5,
            marginBottom: 12,
            display: '-webkit-box',
            WebkitLineClamp: 2,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
          }}
        >
          {project.last_message_preview}
        </p>
      )}
      <div style={{ display: 'flex', gap: 5, marginBottom: 12, flexWrap: 'wrap' }}>
        {project.pending_changes.total > 0 && (
          <Tag>
            {project.pending_changes.total} pending
            {project.pending_changes.has_conflicts ? ' · conflicts' : ''}
          </Tag>
        )}
        {project.report_versions > 1 && <Tag>v{project.report_versions}</Tag>}
        {project.questions_summary.vague_count > 0 && (
          <Tag>{project.questions_summary.vague_count} vague</Tag>
        )}
      </div>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 10,
        }}
      >
        <StatusDot status={status} />
        <div style={{ display: 'flex', gap: 12 }}>
          <Stat
            icon="warn"
            val={risks}
            color={risks >= 4 ? 'var(--danger)' : risks >= 2 ? 'var(--warn)' : 'var(--ok)'}
          />
          <Stat icon="q" val={questions} />
        </div>
      </div>
      <div
        style={{
          paddingTop: 10,
          borderTop: '1px solid var(--border)',
          display: 'flex',
          justifyContent: 'space-between',
        }}
      >
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 10,
            color: 'var(--fg-muted)',
          }}
        >
          {scorePct}% ready
        </span>
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 10,
            color: 'var(--fg-muted)',
          }}
        >
          {timeAgo(project.modified_at)}
        </span>
      </div>
    </div>
  );
}
