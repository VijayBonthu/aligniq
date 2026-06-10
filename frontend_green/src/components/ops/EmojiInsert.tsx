import React, { RefObject, Suspense } from 'react';
import { Popover, PopoverButton, PopoverPanel } from '@headlessui/react';
import type { EmojiClickData, Theme, EmojiStyle } from 'emoji-picker-react';

// Lazy-loaded so the (sizeable) emoji data only downloads when a staffer actually opens
// a picker on the /admin route — it never weighs down the main app bundle.
// `import type` for the enums keeps them out of the eager bundle too (cast below).
const EmojiPicker = React.lazy(() => import('emoji-picker-react'));

/**
 * Full searchable emoji picker (categories + search, like a phone keyboard) that inserts
 * the chosen emoji at the caret of an associated text input/textarea. Native Unicode
 * output, so it stores (Postgres UTF8 / JSONB) and renders (React) through the path we
 * already verified. Generic over the element type so input & textarea both type-check.
 */
export default function EmojiInsert<T extends HTMLInputElement | HTMLTextAreaElement>({
  targetRef,
  value,
  onChange,
}: {
  targetRef: RefObject<T | null>;
  value: string;
  onChange: (next: string) => void;
}) {
  const insert = (emoji: string, close: () => void) => {
    const el = targetRef.current;
    // Selection is preserved across the input's blur, so reading it here (after the
    // popover took focus) still reflects where the user's caret was.
    const start = el?.selectionStart ?? value.length;
    const end = el?.selectionEnd ?? value.length;
    onChange(value.slice(0, start) + emoji + value.slice(end));
    const pos = start + emoji.length;
    requestAnimationFrame(() => {
      if (!el) return;
      el.focus();
      try { el.setSelectionRange(pos, pos); } catch { /* element may not support selection */ }
    });
    close();
  };

  return (
    <Popover style={{ position: 'relative' }}>
      <PopoverButton
        type="button"
        aria-label="Insert emoji"
        title="Insert emoji"
        style={{
          background: 'none', border: 'none', cursor: 'pointer',
          fontSize: 16, lineHeight: 1, padding: '2px 4px', color: 'var(--fg-muted)',
        }}
      >
        😊
      </PopoverButton>
      <PopoverPanel anchor="bottom end" style={{ zIndex: 80, marginTop: 6 }}>
        {({ close }) => (
          <Suspense
            fallback={
              <div style={{
                padding: 16, fontSize: 13, color: 'var(--fg-dim)',
                background: 'var(--surface, #1c1c25)', border: '1px solid var(--border-strong, rgba(220,210,180,0.18))',
                borderRadius: 10,
              }}>Loading…</div>
            }
          >
            <EmojiPicker
              onEmojiClick={(d: EmojiClickData) => insert(d.emoji, close)}
              theme={'dark' as unknown as Theme}
              emojiStyle={'native' as unknown as EmojiStyle}
              lazyLoadEmojis
              previewConfig={{ showPreview: false }}
              width={300}
              height={380}
            />
          </Suspense>
        )}
      </PopoverPanel>
    </Popover>
  );
}
