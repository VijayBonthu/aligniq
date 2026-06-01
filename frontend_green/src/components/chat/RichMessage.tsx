import { useRef } from 'react';
import { toast } from 'react-hot-toast';
import MarkdownContent from './MarkdownContent';
import ReportContent from '../report/ReportContent';
import ReportToolbar from '../report/ReportToolbar';
import { exportMarkdownToPdf } from '../../utils/exportPdf';

export interface ChatMessage {
  id: string | number;
  role: 'user' | 'assistant';
  content: string;
  ts?: string;
  selected?: boolean;
  type?: string;
  reportTitle?: string;
  /** Set when a briefing/analysis tool produced this reply — drives the saved badge + export. */
  savedLabel?: string;
}

interface Props {
  msg: ChatMessage;
  contextMode: boolean;
  onToggleSelect: () => void;
  /** Queue the message content as a draft pending change (analysis/optimization replies). */
  onQueueChange?: (text: string) => void;
  /** This reply is still streaming — defer diagram rendering until complete. */
  streaming?: boolean;
}

// Saved-output labels whose content is actionable as a report change.
const ACTIONABLE_LABELS = new Set(['Cost Analysis', 'Timeline Analysis', 'Optimization']);

export default function RichMessage({ msg, contextMode, onToggleSelect, onQueueChange, streaming }: Props) {
  const isUser = msg.role === 'user';
  const selected = msg.selected !== false;
  const opacity = contextMode && !selected ? 0.4 : 1;
  const isReport = msg.type === 'full_report';
  const reportRef = useRef<HTMLDivElement | null>(null);

  const exportSaved = async () => {
    try {
      const slug = (msg.savedLabel || 'briefing').toLowerCase().replace(/\s+/g, '-');
      await exportMarkdownToPdf(msg.content, `${slug}.pdf`, { title: msg.savedLabel || 'Briefing' });
    } catch {
      toast.error('Export failed');
    }
  };

  return (
    <div
      style={{
        display: 'flex',
        gap: 10,
        flexDirection: isUser ? 'row-reverse' : 'row',
        animation: 'fadeUp .2s ease',
        marginBottom: 14,
        position: 'relative',
      }}
    >
      {contextMode && (
        <div
          style={{
            position: 'absolute',
            left: isUser ? 'auto' : -28,
            right: isUser ? -28 : 'auto',
            top: 6,
            zIndex: 2,
          }}
        >
          <input
            type="checkbox"
            checked={selected}
            onChange={onToggleSelect}
            style={{ width: 14, height: 14, accentColor: 'var(--accent)', cursor: 'pointer' }}
          />
        </div>
      )}
      <div
        style={{
          width: 28,
          height: 28,
          borderRadius: '50%',
          flexShrink: 0,
          background: isUser ? 'var(--accent-soft)' : 'var(--surface-2)',
          border: `1px solid ${isUser ? 'rgba(52,163,123,.3)' : 'var(--border)'}`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: 10,
          color: isUser ? 'var(--accent)' : 'var(--fg-muted)',
          fontWeight: 600,
          fontFamily: 'var(--font-mono)',
        }}
      >
        {isUser ? 'U' : 'A'}
      </div>
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: 4,
          maxWidth: isUser ? '72%' : '90%',
          flex: isUser ? 'none' : 1,
        }}
      >
        <div
          style={{
            padding: '10px 14px',
            borderRadius: isUser ? '12px 4px 12px 12px' : '4px 12px 12px 12px',
            background: isUser ? 'var(--accent-soft)' : 'var(--surface)',
            border: `1px solid ${isUser ? 'rgba(52,163,123,.2)' : 'var(--border)'}`,
            color: 'var(--fg)',
            opacity,
            transition: 'opacity .2s',
          }}
        >
          {isUser ? (
            <p style={{ margin: 0, fontSize: 13.5, whiteSpace: 'pre-wrap' }}>{msg.content}</p>
          ) : isReport ? (
            <>
              <ReportToolbar
                getReportNode={() => reportRef.current}
                markdown={msg.content}
                title={msg.reportTitle || 'Full report'}
              />
              <ReportContent ref={reportRef} content={msg.content} variant="report" />
            </>
          ) : (
            <MarkdownContent content={msg.content} streaming={streaming} />
          )}
        </div>
        {!isUser && !isReport && msg.savedLabel && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 2 }}>
            <span
              style={{
                fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '.06em',
                padding: '2px 7px', borderRadius: 999, background: 'var(--surface-2)',
                border: '1px solid var(--border)', color: 'var(--fg-muted)',
              }}
            >
              ★ {msg.savedLabel}
            </span>
            <div style={{ flex: 1 }} />
            {onQueueChange && ACTIONABLE_LABELS.has(msg.savedLabel) && (
              <button
                onClick={() => onQueueChange(msg.content)}
                style={{
                  background: 'var(--accent-soft)', border: '1px solid var(--accent)', color: 'var(--accent)',
                  borderRadius: 999, fontFamily: 'var(--font-mono)', fontSize: 10, padding: '3px 9px', cursor: 'pointer',
                }}
              >
                Queue as change
              </button>
            )}
            <button
              onClick={exportSaved}
              style={{
                background: 'transparent', border: '1px solid var(--border-strong)', color: 'var(--fg-dim)',
                borderRadius: 999, fontFamily: 'var(--font-mono)', fontSize: 10, padding: '3px 9px', cursor: 'pointer',
              }}
            >
              Export PDF
            </button>
          </div>
        )}
        {msg.ts && (
          <p
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 9,
              color: 'var(--fg-muted)',
              margin: 0,
              paddingLeft: isUser ? 0 : 2,
              textAlign: isUser ? 'right' : 'left',
              letterSpacing: '.04em',
            }}
          >
            {msg.ts}
          </p>
        )}
      </div>
    </div>
  );
}
