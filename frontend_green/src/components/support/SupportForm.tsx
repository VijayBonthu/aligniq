import { useEffect, useId, useMemo, useState, type CSSProperties } from 'react';
import { toast } from 'react-hot-toast';
import { submitSupportRequest, type SupportCategory } from '../../services/supportService';

// Where requests are routed — matches the backend SUPPORT_INBOX. Shown so users
// know it reaches our support desk, not an individual.
const SUPPORT_EMAIL = 'support@grounded-iq.com';

interface Props {
  /** Called after a successful submit — lets a host modal auto-close. */
  onDone?: () => void;
}

const CATEGORIES: { value: SupportCategory; label: string }[] = [
  { value: 'bug', label: 'Bug' },
  { value: 'idea', label: 'Feedback / idea' },
  { value: 'question', label: 'Question / help' },
  { value: 'billing', label: 'Billing' },
];

const MAX_FILES = 3;
const MAX_BYTES = 5 * 1024 * 1024;

const field: CSSProperties = {
  width: '100%',
  boxSizing: 'border-box',
  padding: '10px 12px',
  background: 'var(--bg)',
  border: '1px solid var(--border-strong)',
  borderRadius: 'var(--radius)',
  color: 'var(--fg)',
  fontSize: 13.5,
  fontFamily: 'var(--font-sans)',
  outline: 'none',
};

const label: CSSProperties = {
  display: 'block',
  fontSize: 12,
  color: 'var(--fg-dim)',
  marginBottom: 7,
  fontWeight: 500,
};

export default function SupportForm({ onDone }: Props) {
  const inputId = useId();

  const [category, setCategory] = useState<SupportCategory>('bug');
  const [subject, setSubject] = useState('');
  const [message, setMessage] = useState('');
  const [screenshots, setScreenshots] = useState<File[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [doneRef, setDoneRef] = useState<string | null>(null);

  const previews = useMemo(
    () => screenshots.map(f => ({ file: f, url: URL.createObjectURL(f) })),
    [screenshots],
  );
  useEffect(() => () => previews.forEach(p => URL.revokeObjectURL(p.url)), [previews]);

  function addFiles(list: FileList | null) {
    if (!list) return;
    const accepted: File[] = [];
    for (const f of Array.from(list)) {
      if (!f.type.startsWith('image/')) { toast.error(`${f.name} isn't an image`); continue; }
      if (f.size > MAX_BYTES) { toast.error(`${f.name} is over 5 MB`); continue; }
      accepted.push(f);
    }
    setScreenshots(prev => {
      if (prev.length + accepted.length > MAX_FILES) toast.error(`Up to ${MAX_FILES} screenshots`);
      return [...prev, ...accepted].slice(0, MAX_FILES);
    });
  }

  function removeFile(idx: number) {
    setScreenshots(prev => prev.filter((_, i) => i !== idx));
  }

  function reset() {
    setDoneRef(null);
    setCategory('bug');
    setSubject('');
    setMessage('');
    setScreenshots([]);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!subject.trim() || !message.trim() || submitting) return;
    setSubmitting(true);
    try {
      const res = await submitSupportRequest({
        category,
        subject: subject.trim(),
        message: message.trim(),
        screenshots,
      });
      toast.success("Request sent — we'll be in touch.");
      setDoneRef(res.ref_code);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not send your request.');
    } finally {
      setSubmitting(false);
    }
  }

  // ---- success panel ----
  if (doneRef) {
    return (
      <div style={{ textAlign: 'center', padding: '12px 4px' }}>
        <div
          style={{
            width: 46, height: 46, borderRadius: '50%', margin: '0 auto 16px',
            background: 'var(--accent-soft)', border: '1px solid rgba(52,163,123,.3)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}
        >
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
            <path d="M20 6 9 17l-5-5" />
          </svg>
        </div>
        <h3 className="display" style={{ fontSize: 20, margin: '0 0 8px', color: 'var(--fg)' }}>
          Thanks — we got it.
        </h3>
        <p style={{ fontSize: 13.5, color: 'var(--fg-dim)', margin: '0 0 6px', lineHeight: 1.6 }}>
          Our team will reply to the email on your account.
        </p>
        <p style={{ fontSize: 12.5, color: 'var(--fg-muted)', margin: '0 0 22px', fontFamily: 'var(--font-mono)' }}>
          Reference <span style={{ color: 'var(--accent)' }}>{doneRef}</span>
        </p>
        <div style={{ display: 'flex', gap: 10, justifyContent: 'center', flexWrap: 'wrap' }}>
          <button type="button" className="btn btn-ghost" onClick={reset}>
            Submit another
          </button>
          {onDone && (
            <button type="button" className="btn btn-primary" onClick={onDone}>
              Done
            </button>
          )}
        </div>
      </div>
    );
  }

  const canSubmit = !!subject.trim() && !!message.trim() && !submitting;

  return (
    <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      {/* Category */}
      <div>
        <span style={label}>What's this about?</span>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {CATEGORIES.map(c => {
            const active = category === c.value;
            return (
              <button
                key={c.value}
                type="button"
                onClick={() => setCategory(c.value)}
                style={{
                  padding: '7px 13px',
                  borderRadius: 999,
                  fontSize: 12.5,
                  fontFamily: 'var(--font-sans)',
                  cursor: 'pointer',
                  transition: 'all .15s',
                  background: active ? 'var(--accent-soft)' : 'transparent',
                  border: `1px solid ${active ? 'var(--accent)' : 'var(--border-strong)'}`,
                  color: active ? 'var(--fg)' : 'var(--fg-dim)',
                }}
              >
                {c.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Subject */}
      <div>
        <label htmlFor={`${inputId}-subject`} style={label}>Subject</label>
        <input
          id={`${inputId}-subject`}
          type="text"
          value={subject}
          maxLength={200}
          onChange={e => setSubject(e.target.value)}
          placeholder="Short summary of the issue or idea"
          style={field}
        />
      </div>

      {/* Message */}
      <div>
        <label htmlFor={`${inputId}-message`} style={label}>Details</label>
        <textarea
          id={`${inputId}-message`}
          value={message}
          maxLength={5000}
          onChange={e => setMessage(e.target.value)}
          placeholder="What happened, what you expected, and steps to reproduce if it's a bug."
          rows={5}
          style={{ ...field, resize: 'vertical', minHeight: 96, lineHeight: 1.5 }}
        />
      </div>

      {/* Screenshots */}
      <div>
        <span style={label}>Screenshots <span style={{ color: 'var(--fg-muted)' }}>· optional, up to {MAX_FILES}</span></span>
        {previews.length > 0 && (
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 10 }}>
            {previews.map((p, i) => (
              <div
                key={p.url}
                style={{
                  position: 'relative', width: 72, height: 72, borderRadius: 8, overflow: 'hidden',
                  border: '1px solid var(--border-strong)',
                }}
              >
                <img src={p.url} alt={p.file.name} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                <button
                  type="button"
                  onClick={() => removeFile(i)}
                  aria-label={`Remove ${p.file.name}`}
                  style={{
                    position: 'absolute', top: 3, right: 3, width: 18, height: 18, borderRadius: '50%',
                    background: 'rgba(0,0,0,.7)', border: 'none', color: '#fff', cursor: 'pointer',
                    fontSize: 12, lineHeight: '16px', display: 'flex', alignItems: 'center', justifyContent: 'center',
                  }}
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        )}
        {previews.length < MAX_FILES && (
          <>
            <input
              id={inputId}
              type="file"
              accept="image/*"
              multiple
              onChange={e => { addFiles(e.target.files); e.target.value = ''; }}
              style={{ display: 'none' }}
            />
            <label
              htmlFor={inputId}
              onDragOver={e => { e.preventDefault(); setDragOver(true); }}
              onDragLeave={() => setDragOver(false)}
              onDrop={e => { e.preventDefault(); setDragOver(false); addFiles(e.dataTransfer.files); }}
              style={{
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
                padding: '14px 16px', borderRadius: 'var(--radius)', cursor: 'pointer',
                background: dragOver ? 'var(--accent-soft)' : 'var(--bg)',
                border: `1.5px dashed ${dragOver ? 'var(--accent)' : 'var(--border-strong)'}`,
                color: 'var(--fg-dim)', fontSize: 12.5, transition: 'all .15s',
              }}
            >
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                <polyline points="17 8 12 3 7 8" />
                <line x1="12" y1="3" x2="12" y2="15" />
              </svg>
              Drag an image here or click to attach
            </label>
          </>
        )}
      </div>

      {/* Footer */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', marginTop: 2 }}>
        <p style={{ fontSize: 12, color: 'var(--fg-muted)', margin: 0, fontFamily: 'var(--font-mono)' }}>
          Sent to {SUPPORT_EMAIL}
        </p>
        <button type="submit" className="btn btn-primary" disabled={!canSubmit}>
          {submitting ? 'Sending…' : 'Send request'}
        </button>
      </div>
    </form>
  );
}
