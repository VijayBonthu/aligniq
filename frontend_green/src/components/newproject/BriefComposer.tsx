import { useRef, useState } from 'react';
import type { BriefScreenshot } from '../../utils/buildBriefDocx';

export interface ComposerScreenshot extends BriefScreenshot {
  id: string;
}

export interface DraftState {
  title: string;
  body: string;
  screenshots: ComposerScreenshot[];
}

export const EMPTY_DRAFT: DraftState = { title: '', body: '', screenshots: [] };

interface BriefComposerProps {
  draft: DraftState;
  setDraft: React.Dispatch<React.SetStateAction<DraftState>>;
  submitting: boolean;
  onSubmit: () => void;
}

const MIN_BODY = 40;
const MAX_SCREENSHOTS = 12;
const IMAGE_MAX_DIM = 1600;

const SECTION_TEMPLATES: { label: string; md: string }[] = [
  { label: 'Overview', md: '## Overview\nWhat is this project and the problem it solves?\n' },
  { label: 'Goals & success metrics', md: '## Goals & success metrics\n- \n' },
  { label: 'Users & roles', md: '## Users & roles\n- \n' },
  { label: 'Functional requirements', md: '## Functional requirements\n- \n' },
  { label: 'User flows', md: '## User flows\n1. \n' },
  { label: 'Integrations & data', md: '## Integrations & data\n- \n' },
  { label: 'Constraints (non-functional)', md: '## Constraints\n- \n' },
  { label: 'Timeline & budget', md: '## Timeline & budget\n- \n' },
];

const PLACEHOLDER = `Describe the project in your own words — the more concrete, the sharper the scan.

What helps most: the goal and the problem, who uses it and the key flows, must-have features, hard constraints, integrations, timeline and budget.

Tip: paste screenshots of mockups or flows right here — we read them too.`;

let shotSeq = 0;
const nextId = () => `s-${(shotSeq += 1)}-${Math.round(Math.random() * 1e6)}`;

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = reject;
    img.src = src;
  });
}

/** Normalise any pasted/dropped image to a downscaled PNG data URL (consistent
 *  type for docx embed, EXIF stripped, kept well under the 10 MB upload cap). */
async function normalizeToPng(
  blob: Blob,
): Promise<{ dataUrl: string; width: number; height: number } | null> {
  const url = URL.createObjectURL(blob);
  try {
    const img = await loadImage(url);
    let w = img.naturalWidth || img.width;
    let h = img.naturalHeight || img.height;
    if (!w || !h) return null;
    const scale = Math.min(1, IMAGE_MAX_DIM / Math.max(w, h));
    w = Math.round(w * scale);
    h = Math.round(h * scale);
    const canvas = document.createElement('canvas');
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext('2d');
    if (!ctx) return null;
    ctx.drawImage(img, 0, 0, w, h);
    return { dataUrl: canvas.toDataURL('image/png'), width: w, height: h };
  } catch {
    return null;
  } finally {
    URL.revokeObjectURL(url);
  }
}

export default function BriefComposer({ draft, setDraft, submitting, onSubmit }: BriefComposerProps) {
  const { title, body, screenshots } = draft;
  const [sectionMenu, setSectionMenu] = useState(false);
  const [dragOver, setDragOver] = useState(false);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const bodyChars = body.trim().length;
  const canSubmit = bodyChars >= MIN_BODY && !submitting;

  const setTitle = (v: string) => setDraft((d) => ({ ...d, title: v }));
  const setBody = (v: string) => setDraft((d) => ({ ...d, body: v }));

  const insertAtCursor = (text: string) => {
    const ta = textareaRef.current;
    if (!ta) {
      setDraft((d) => ({ ...d, body: d.body + text }));
      return;
    }
    const start = ta.selectionStart ?? body.length;
    const end = ta.selectionEnd ?? body.length;
    const before = body.slice(0, start);
    const lead = before && !before.endsWith('\n') ? '\n' : '';
    const insert = lead + text;
    const next = before + insert + body.slice(end);
    setBody(next);
    requestAnimationFrame(() => {
      ta.focus();
      const pos = start + insert.length;
      ta.setSelectionRange(pos, pos);
    });
  };

  const addImages = async (files: ArrayLike<File> | File[]) => {
    const list = Array.from(files).filter((f) => f.type.startsWith('image/'));
    for (const f of list) {
      const norm = await normalizeToPng(f);
      if (!norm) continue;
      setDraft((d) =>
        d.screenshots.length >= MAX_SCREENSHOTS
          ? d
          : { ...d, screenshots: [...d.screenshots, { id: nextId(), caption: '', ...norm }] },
      );
    }
  };

  const onPaste = (e: React.ClipboardEvent) => {
    const items = e.clipboardData?.items;
    if (!items) return;
    const imgs: File[] = [];
    for (let i = 0; i < items.length; i += 1) {
      const it = items[i];
      if (it.type.startsWith('image/')) {
        const f = it.getAsFile();
        if (f) imgs.push(f);
      }
    }
    if (imgs.length) {
      e.preventDefault();
      void addImages(imgs);
    }
  };

  const updateCaption = (id: string, caption: string) =>
    setDraft((d) => ({
      ...d,
      screenshots: d.screenshots.map((s) => (s.id === id ? { ...s, caption } : s)),
    }));
  const removeShot = (id: string) =>
    setDraft((d) => ({ ...d, screenshots: d.screenshots.filter((s) => s.id !== id) }));

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div
        onDragOver={(e) => {
          e.preventDefault();
          if (!dragOver) setDragOver(true);
        }}
        onDragLeave={(e) => {
          if (e.currentTarget === e.target) setDragOver(false);
        }}
        onDrop={(e) => {
          if (e.dataTransfer?.files?.length) {
            e.preventDefault();
            setDragOver(false);
            void addImages(e.dataTransfer.files);
          }
        }}
        style={{
          background: 'var(--surface)',
          border: `1px solid ${dragOver ? 'var(--accent)' : 'var(--border)'}`,
          borderRadius: 16,
          overflow: 'hidden',
          transition: 'border-color .15s',
          position: 'relative',
        }}
      >
        {/* Title */}
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Project name"
          style={{
            width: '100%',
            border: 'none',
            outline: 'none',
            background: 'transparent',
            color: 'var(--fg)',
            fontFamily: 'var(--font-display)',
            fontSize: 22,
            fontWeight: 400,
            letterSpacing: '-.01em',
            padding: '18px 22px 12px',
          }}
        />

        {/* Toolbar */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            padding: '8px 16px',
            borderTop: '1px solid var(--border)',
            borderBottom: '1px solid var(--border)',
            flexWrap: 'wrap',
          }}
        >
          <ToolbarButton label="Heading" onClick={() => insertAtCursor('## ')}>
            <span style={{ fontWeight: 700, fontSize: 13 }}>H</span>
          </ToolbarButton>
          <ToolbarButton label="Bullet list" onClick={() => insertAtCursor('- ')}>
            <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <circle cx="4" cy="6" r="1.4" fill="currentColor" stroke="none" />
              <circle cx="4" cy="12" r="1.4" fill="currentColor" stroke="none" />
              <circle cx="4" cy="18" r="1.4" fill="currentColor" stroke="none" />
              <path d="M9 6h11M9 12h11M9 18h11" strokeWidth="1.8" strokeLinecap="round" />
            </svg>
          </ToolbarButton>
          <ToolbarButton label="Numbered list" onClick={() => insertAtCursor('1. ')}>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 600 }}>1.</span>
          </ToolbarButton>

          <div style={{ width: 1, height: 18, background: 'var(--border)', margin: '0 4px' }} />

          <div style={{ position: 'relative' }}>
            <ToolbarButton label="Insert section" wide onClick={() => setSectionMenu((v) => !v)}>
              <svg width="13" height="13" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path d="M12 5v14M5 12h14" strokeWidth="2" strokeLinecap="round" />
              </svg>
              <span style={{ fontSize: 12.5 }}>Section</span>
              <svg width="11" height="11" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path d="M6 9l6 6 6-6" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </ToolbarButton>
            {sectionMenu && (
              <>
                <div
                  onClick={() => setSectionMenu(false)}
                  style={{ position: 'fixed', inset: 0, zIndex: 20 }}
                />
                <div
                  style={{
                    position: 'absolute',
                    top: 'calc(100% + 6px)',
                    left: 0,
                    zIndex: 21,
                    width: 230,
                    background: 'var(--surface-2)',
                    border: '1px solid var(--border-strong)',
                    borderRadius: 10,
                    boxShadow: 'var(--shadow-card)',
                    padding: 6,
                  }}
                >
                  {SECTION_TEMPLATES.map((s) => (
                    <button
                      key={s.label}
                      type="button"
                      onClick={() => {
                        insertAtCursor(`${s.md}\n`);
                        setSectionMenu(false);
                      }}
                      style={{
                        display: 'block',
                        width: '100%',
                        textAlign: 'left',
                        padding: '8px 10px',
                        background: 'transparent',
                        border: 'none',
                        borderRadius: 7,
                        color: 'var(--fg-dim)',
                        fontSize: 12.5,
                        cursor: 'pointer',
                        fontFamily: 'var(--font-sans)',
                      }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.background = 'var(--surface)';
                        e.currentTarget.style.color = 'var(--fg)';
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.background = 'transparent';
                        e.currentTarget.style.color = 'var(--fg-dim)';
                      }}
                    >
                      {s.label}
                    </button>
                  ))}
                </div>
              </>
            )}
          </div>

          <div style={{ flex: 1 }} />

          <ToolbarButton label="Add screenshot" wide onClick={() => fileRef.current?.click()}>
            <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <rect x="3" y="5" width="18" height="14" rx="2" strokeWidth="1.8" />
              <circle cx="8.5" cy="10" r="1.5" strokeWidth="1.6" />
              <path d="M21 16l-5-5L5 21" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            <span style={{ fontSize: 12.5 }}>Screenshot</span>
          </ToolbarButton>
          <input
            ref={fileRef}
            type="file"
            accept="image/*"
            multiple
            onChange={(e) => {
              if (e.target.files?.length) void addImages(e.target.files);
              e.target.value = '';
            }}
            style={{ display: 'none' }}
          />
        </div>

        {/* Editor */}
        <textarea
          ref={textareaRef}
          value={body}
          onChange={(e) => setBody(e.target.value)}
          onPaste={onPaste}
          placeholder={PLACEHOLDER}
          spellCheck
          style={{
            width: '100%',
            minHeight: 320,
            resize: 'vertical',
            border: 'none',
            outline: 'none',
            background: 'transparent',
            color: 'var(--fg)',
            fontFamily: 'var(--font-sans)',
            fontSize: 14.5,
            lineHeight: 1.7,
            padding: '18px 22px',
            display: 'block',
          }}
        />

        {/* Screenshot tray */}
        {screenshots.length > 0 && (
          <div style={{ padding: '4px 16px 18px', borderTop: '1px solid var(--border)' }}>
            <p
              className="label-mono"
              style={{ fontSize: 9, margin: '14px 6px 10px', color: 'var(--fg-muted)' }}
            >
              SCREENSHOTS · {screenshots.length}
            </p>
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fill, minmax(min(160px, 100%), 1fr))',
                gap: 10,
              }}
            >
              {screenshots.map((s, i) => (
                <div
                  key={s.id}
                  style={{
                    border: '1px solid var(--border)',
                    borderRadius: 10,
                    overflow: 'hidden',
                    background: 'var(--bg-2)',
                  }}
                >
                  <div style={{ position: 'relative' }}>
                    <img
                      src={s.dataUrl}
                      alt={s.caption || `Screenshot ${i + 1}`}
                      style={{ width: '100%', height: 96, objectFit: 'cover', display: 'block' }}
                    />
                    <span
                      style={{
                        position: 'absolute',
                        top: 6,
                        left: 6,
                        fontFamily: 'var(--font-mono)',
                        fontSize: 9,
                        padding: '2px 6px',
                        borderRadius: 5,
                        background: 'rgba(0,0,0,.55)',
                        color: '#fff',
                      }}
                    >
                      FIG {i + 1}
                    </span>
                    <button
                      type="button"
                      onClick={() => removeShot(s.id)}
                      aria-label="Remove screenshot"
                      style={{
                        position: 'absolute',
                        top: 6,
                        right: 6,
                        width: 22,
                        height: 22,
                        borderRadius: '50%',
                        border: 'none',
                        background: 'rgba(0,0,0,.55)',
                        color: '#fff',
                        cursor: 'pointer',
                        fontSize: 13,
                        lineHeight: 1,
                      }}
                    >
                      ×
                    </button>
                  </div>
                  <input
                    value={s.caption}
                    onChange={(e) => updateCaption(s.id, e.target.value)}
                    placeholder="Describe this screen / flow…"
                    style={{
                      width: '100%',
                      border: 'none',
                      borderTop: '1px solid var(--border)',
                      outline: 'none',
                      background: 'transparent',
                      color: 'var(--fg)',
                      fontSize: 12,
                      padding: '8px 10px',
                    }}
                  />
                </div>
              ))}
            </div>
          </div>
        )}

        {dragOver && (
          <div
            style={{
              position: 'absolute',
              inset: 0,
              background: 'var(--accent-soft)',
              border: '2px dashed var(--accent)',
              borderRadius: 16,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              pointerEvents: 'none',
              color: 'var(--accent)',
              fontSize: 14,
              fontWeight: 500,
            }}
          >
            Drop screenshots to attach
          </div>
        )}
      </div>

      {/* Footer */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 16,
          flexWrap: 'wrap',
        }}
      >
        <p style={{ fontSize: 12, color: 'var(--fg-muted)', margin: 0, maxWidth: 460, lineHeight: 1.5 }}>
          Packaged as a structured brief — screenshots are read too. Markdown supported.
          {bodyChars < MIN_BODY && ' Add a little more detail to begin.'}
        </p>
        <button
          type="button"
          onClick={onSubmit}
          disabled={!canSubmit}
          style={{
            minWidth: 200,
            padding: '11px 20px',
            borderRadius: 10,
            border: 'none',
            background: canSubmit ? 'var(--accent)' : 'var(--surface-2)',
            color: canSubmit ? 'var(--accent-ink)' : 'var(--fg-muted)',
            fontFamily: 'var(--font-display)',
            fontSize: 14,
            fontWeight: 500,
            cursor: canSubmit ? 'pointer' : 'not-allowed',
            display: 'inline-flex',
            alignItems: 'center',
            gap: 8,
            justifyContent: 'center',
            boxShadow: canSubmit ? 'var(--glow)' : 'none',
            transition: 'all .15s',
          }}
        >
          {submitting ? 'Packaging…' : 'Analyse brief →'}
        </button>
      </div>
    </div>
  );
}

function ToolbarButton({
  label,
  onClick,
  children,
  wide,
}: {
  label: string;
  onClick: () => void;
  children: React.ReactNode;
  wide?: boolean;
}) {
  const [hov, setHov] = useState(false);
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      onClick={onClick}
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        height: 30,
        padding: wide ? '0 10px' : '0',
        width: wide ? 'auto' : 30,
        justifyContent: 'center',
        borderRadius: 7,
        border: '1px solid transparent',
        background: hov ? 'var(--surface-2)' : 'transparent',
        color: hov ? 'var(--fg)' : 'var(--fg-dim)',
        cursor: 'pointer',
        transition: 'all .12s',
        fontFamily: 'var(--font-sans)',
      }}
    >
      {children}
    </button>
  );
}
