import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Sev } from '../ui/Chips';
import type { InboxQuestion } from '../../types/overview';

interface Props {
  item: InboxQuestion;
}

export default function InboxRow({ item }: Props) {
  const navigate = useNavigate();
  const [hov, setHov] = useState(false);
  const isP1 = item.question_type === 'p1_blocker';

  return (
    <button
      type="button"
      onClick={() =>
        navigate(`/dashboard/${item.chat_history_id}?focus=question-${item.question_id}`)
      }
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      style={{
        width: '100%',
        textAlign: 'left',
        padding: '11px 13px',
        background: hov ? 'var(--surface-2)' : 'var(--surface)',
        border: `1px solid ${hov ? 'var(--border-strong)' : 'var(--border)'}`,
        borderLeft: `2px solid ${isP1 ? 'var(--danger)' : 'var(--warn)'}`,
        borderRadius: 'var(--radius)',
        cursor: 'pointer',
        transition: 'all .12s',
        display: 'flex',
        flexDirection: 'column',
        gap: 5,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <Sev level={isP1 ? 'HIGH' : 'MED'} />
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 9,
            color: 'var(--fg-muted)',
            letterSpacing: '.08em',
          }}
        >
          {item.question_number}
        </span>
        {item.area_or_category && (
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 9,
              color: 'var(--fg-muted)',
              letterSpacing: '.08em',
              textTransform: 'uppercase',
              padding: '1px 6px',
              borderRadius: 3,
              background: 'var(--surface)',
              border: '1px solid var(--border)',
            }}
          >
            {item.area_or_category}
          </span>
        )}
      </div>
      <p
        style={{
          fontSize: 12.5,
          color: 'var(--fg)',
          margin: 0,
          lineHeight: 1.4,
          display: '-webkit-box',
          WebkitLineClamp: 2,
          WebkitBoxOrient: 'vertical',
          overflow: 'hidden',
        }}
      >
        {item.title || item.question_text}
      </p>
      <p
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 10,
          color: 'var(--fg-muted)',
          margin: 0,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}
      >
        {item.project_title}
      </p>
    </button>
  );
}
