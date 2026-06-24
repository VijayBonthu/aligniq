import { useMemo, useState } from 'react';
import ProjectCard from './ProjectCard';
import NewProjectCard from './NewProjectCard';
import type { ProjectRow } from '../../types/overview';

type Filter = 'all' | 'attention' | 'analyzing' | 'ready';
type SortKey = 'recent' | 'readiness' | 'attention';

const FILTERS: { key: Filter; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'attention', label: 'Needs attention' },
  { key: 'analyzing', label: 'Analyzing' },
  { key: 'ready', label: 'Ready' },
];

const SORTS: { key: SortKey; label: string }[] = [
  { key: 'recent', label: 'Recently updated' },
  { key: 'readiness', label: 'Readiness' },
  { key: 'attention', label: 'Most blockers' },
];

function openBlockers(p: ProjectRow): number {
  return Math.max(0, p.questions_summary.p1_total - p.questions_summary.p1_answered);
}
function isAnalyzing(p: ProjectRow): boolean {
  return p.pipeline_status === 'running' || p.pipeline_status === 'queued';
}
function needsAttention(p: ProjectRow): boolean {
  return (
    openBlockers(p) > 0 ||
    p.pending_changes.has_conflicts ||
    p.readiness.status === 'needs_more_info'
  );
}
function isReady(p: ProjectRow): boolean {
  return p.readiness.status === 'ready';
}
function matchesFilter(p: ProjectRow, f: Filter): boolean {
  if (f === 'attention') return needsAttention(p);
  if (f === 'analyzing') return isAnalyzing(p);
  if (f === 'ready') return isReady(p);
  return true;
}

interface Props {
  projects: ProjectRow[];
  onRenamed?: (chatHistoryId: string, customTitle: string | null) => void;
}

export default function CardGrid({ projects, onRenamed }: Props) {
  const [filter, setFilter] = useState<Filter>('all');
  const [sort, setSort] = useState<SortKey>('recent');
  const [query, setQuery] = useState('');
  const [searchFocused, setSearchFocused] = useState(false);

  const counts = useMemo(
    () => ({
      all: projects.length,
      attention: projects.filter(needsAttention).length,
      analyzing: projects.filter(isAnalyzing).length,
      ready: projects.filter(isReady).length,
    }),
    [projects],
  );

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    let list = projects.filter((p) => matchesFilter(p, filter));
    if (q) {
      list = list.filter(
        (p) =>
          p.title.toLowerCase().includes(q) ||
          (p.custom_title || '').toLowerCase().includes(q) ||
          (p.last_message_preview || '').toLowerCase().includes(q),
      );
    }
    const sorted = [...list];
    if (sort === 'recent') {
      sorted.sort(
        (a, b) =>
          (Date.parse(b.modified_at || '') || 0) - (Date.parse(a.modified_at || '') || 0),
      );
    } else if (sort === 'readiness') {
      sorted.sort((a, b) => a.readiness.score - b.readiness.score);
    } else if (sort === 'attention') {
      sorted.sort((a, b) => openBlockers(b) - openBlockers(a));
    }
    return sorted;
  }, [projects, filter, query, sort]);

  const showNewCard = filter === 'all' && query.trim() === '';
  const isFiltered = filter !== 'all' || query.trim() !== '';

  return (
    <div
      style={{
        flex: 1,
        overflowY: 'auto',
        padding: '22px clamp(16px, 4vw, 30px) 30px',
        animation: 'fadeIn .25s ease',
      }}
    >
      {/* Toolbar: search · filter pills · sort */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          marginBottom: 20,
          flexWrap: 'wrap',
        }}
      >
        <div style={{ position: 'relative', flex: '0 1 300px', minWidth: 200 }}>
          <svg
            width="14"
            height="14"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
            style={{
              position: 'absolute',
              left: 12,
              top: '50%',
              transform: 'translateY(-50%)',
              color: 'var(--fg-muted)',
              pointerEvents: 'none',
            }}
          >
            <circle cx="11" cy="11" r="7" strokeWidth="1.8" />
            <path d="M21 21l-4.3-4.3" strokeWidth="1.8" strokeLinecap="round" />
          </svg>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onFocus={() => setSearchFocused(true)}
            onBlur={() => setSearchFocused(false)}
            placeholder="Search projects…"
            style={{
              width: '100%',
              padding: '9px 32px 9px 34px',
              borderRadius: 10,
              background: 'var(--surface)',
              border: `1px solid ${searchFocused ? 'var(--accent)' : 'var(--border)'}`,
              color: 'var(--fg)',
              fontSize: 13,
              fontFamily: 'var(--font-sans)',
              outline: 'none',
              transition: 'border-color .15s',
            }}
          />
          {query && (
            <button
              type="button"
              onClick={() => setQuery('')}
              aria-label="Clear search"
              style={{
                position: 'absolute',
                right: 8,
                top: '50%',
                transform: 'translateY(-50%)',
                width: 18,
                height: 18,
                borderRadius: '50%',
                border: 'none',
                background: 'var(--surface-2)',
                color: 'var(--fg-muted)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: 'pointer',
                fontSize: 12,
                lineHeight: 1,
              }}
            >
              ×
            </button>
          )}
        </div>

        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {FILTERS.map((f) => {
            const active = filter === f.key;
            const c = counts[f.key];
            return (
              <button
                key={f.key}
                onClick={() => setFilter(f.key)}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 6,
                  padding: '6px 12px',
                  borderRadius: 999,
                  border: `1px solid ${active ? 'transparent' : 'var(--border)'}`,
                  background: active ? 'var(--accent-soft)' : 'transparent',
                  color: active ? 'var(--accent)' : 'var(--fg-dim)',
                  fontSize: 12.5,
                  fontWeight: 500,
                  cursor: 'pointer',
                  transition: 'all .15s',
                  whiteSpace: 'nowrap',
                  fontFamily: 'var(--font-sans)',
                }}
              >
                {f.label}
                <span
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: 10,
                    color:
                      f.key === 'attention' && c > 0 && !active
                        ? 'var(--warn)'
                        : active
                        ? 'var(--accent)'
                        : 'var(--fg-muted)',
                  }}
                >
                  {c}
                </span>
              </button>
            );
          })}
        </div>

        <div style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 8 }}>
          <span className="label-mono" style={{ fontSize: 9 }}>
            Sort
          </span>
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value as SortKey)}
            style={{
              background: 'var(--surface)',
              color: 'var(--fg)',
              border: '1px solid var(--border)',
              borderRadius: 8,
              padding: '7px 10px',
              fontSize: 12.5,
              fontFamily: 'var(--font-sans)',
              cursor: 'pointer',
              outline: 'none',
            }}
          >
            {SORTS.map((s) => (
              <option key={s.key} value={s.key}>
                {s.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {filtered.length === 0 && !showNewCard ? (
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: 10,
            padding: '64px 20px',
            textAlign: 'center',
          }}
        >
          <div
            style={{
              width: 40,
              height: 40,
              borderRadius: '50%',
              background: 'var(--surface)',
              border: '1px solid var(--border)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'var(--fg-muted)',
            }}
          >
            <svg width="18" height="18" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <circle cx="11" cy="11" r="7" strokeWidth="1.8" />
              <path d="M21 21l-4.3-4.3" strokeWidth="1.8" strokeLinecap="round" />
            </svg>
          </div>
          <p style={{ fontSize: 13.5, color: 'var(--fg)', margin: 0 }}>No projects match</p>
          <p style={{ fontSize: 12, color: 'var(--fg-muted)', margin: 0 }}>
            Try a different filter or search term.
          </p>
          {isFiltered && (
            <button
              type="button"
              onClick={() => {
                setFilter('all');
                setQuery('');
              }}
              style={{
                marginTop: 4,
                padding: '7px 14px',
                borderRadius: 999,
                border: '1px solid var(--border-strong)',
                background: 'transparent',
                color: 'var(--fg)',
                fontSize: 12.5,
                cursor: 'pointer',
                fontFamily: 'var(--font-sans)',
              }}
            >
              Clear filters
            </button>
          )}
        </div>
      ) : (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(min(280px, 100%), 1fr))',
            gap: 14,
          }}
        >
          {filtered.map((p, i) => (
            <ProjectCard key={p.chat_history_id} project={p} delay={Math.min(i, 12) * 40} onRenamed={onRenamed} />
          ))}
          {showNewCard && <NewProjectCard />}
        </div>
      )}
    </div>
  );
}
