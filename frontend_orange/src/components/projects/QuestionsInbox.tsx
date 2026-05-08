import { useMemo } from 'react';
import InboxRow from './InboxRow';
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
    <aside
      style={{
        width: 320,
        flexShrink: 0,
        borderLeft: '1px solid var(--border)',
        background: 'var(--surface)',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}
    >
      <div
        style={{
          padding: '22px 22px 14px',
          borderBottom: '1px solid var(--border)',
        }}
      >
        <p
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 10,
            letterSpacing: '.14em',
            textTransform: 'uppercase',
            color: 'var(--fg-muted)',
            margin: 0,
          }}
        >
          QUESTIONS INBOX
        </p>
        <div
          style={{
            display: 'flex',
            alignItems: 'baseline',
            justifyContent: 'space-between',
            marginTop: 3,
          }}
        >
          <h2
            style={{
              fontFamily: 'var(--font-display)',
              fontSize: 18,
              fontWeight: 400,
              letterSpacing: '-.01em',
              color: 'var(--fg)',
              margin: 0,
            }}
          >
            Unanswered
          </h2>
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 11,
              color: 'var(--fg-muted)',
              padding: '1px 8px',
              borderRadius: 999,
              background: 'var(--surface-2)',
              border: '1px solid var(--border)',
            }}
          >
            {inbox.length}
          </span>
        </div>
      </div>

      <div
        style={{
          flex: 1,
          overflowY: 'auto',
          padding: '16px 16px 22px',
          display: 'flex',
          flexDirection: 'column',
          gap: 18,
        }}
      >
        {inbox.length === 0 ? (
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: 8,
              padding: '40px 10px',
              textAlign: 'center',
            }}
          >
            <div
              style={{
                width: 40,
                height: 40,
                borderRadius: '50%',
                background: 'color-mix(in oklab, var(--ok) 14%, transparent)',
                border: '1px solid color-mix(in oklab, var(--ok) 30%, transparent)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: 'var(--ok)',
              }}
            >
              <svg width="18" height="18" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path d="M5 13l4 4L19 7" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>
            <p style={{ fontSize: 13, color: 'var(--fg)', margin: 0 }}>Inbox zero</p>
            <p style={{ fontSize: 11.5, color: 'var(--fg-muted)', margin: 0 }}>
              No unanswered questions.
            </p>
          </div>
        ) : (
          <>
            {p1.length > 0 && (
              <div>
                <p
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: 9,
                    letterSpacing: '.14em',
                    textTransform: 'uppercase',
                    color: 'var(--danger)',
                    margin: '0 0 9px',
                  }}
                >
                  P1 BLOCKERS · {p1.length}
                </p>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
                  {p1.map((q) => (
                    <InboxRow key={q.question_id} item={q} />
                  ))}
                </div>
              </div>
            )}
            {kickstart.length > 0 && (
              <div>
                <p
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: 9,
                    letterSpacing: '.14em',
                    textTransform: 'uppercase',
                    color: 'var(--warn)',
                    margin: '0 0 9px',
                  }}
                >
                  KICKSTART · {kickstart.length}
                </p>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
                  {kickstart.map((q) => (
                    <InboxRow key={q.question_id} item={q} />
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </aside>
  );
}
