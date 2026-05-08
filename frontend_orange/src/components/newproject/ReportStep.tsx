import { useEffect, useRef, useState } from 'react';
import ReportContent from '../report/ReportContent';
import ReportToolbar from '../report/ReportToolbar';
import { updateReport } from '../../services/presalesService';

interface Props {
  reportContent: string;
  projectTitle: string;
  chatHistoryId: string | null;
  onOpenChat: () => void;
  onBack: () => void;
  onContentChange?: (content: string) => void;
}

export default function ReportStep({
  reportContent,
  projectTitle,
  chatHistoryId,
  onOpenChat,
  onBack,
  onContentChange,
}: Props) {
  const reportRef = useRef<HTMLDivElement | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState(reportContent);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  // Keep draft in sync when parent's reportContent changes (e.g. after regeneration).
  useEffect(() => {
    if (!isEditing) setDraft(reportContent);
  }, [reportContent, isEditing]);

  const handleStartEdit = () => {
    setSaveError(null);
    setDraft(reportContent);
    setIsEditing(true);
  };

  const handleCancel = () => {
    setSaveError(null);
    setDraft(reportContent);
    setIsEditing(false);
  };

  const handleSave = async () => {
    if (!chatHistoryId) {
      setSaveError('Missing chat reference — cannot save.');
      return;
    }
    if (!draft.trim()) {
      setSaveError('Content cannot be empty.');
      return;
    }
    setSaving(true);
    setSaveError(null);
    try {
      await updateReport(chatHistoryId, draft);
      onContentChange?.(draft);
      setIsEditing(false);
    } catch (err: unknown) {
      const message =
        err && typeof err === 'object' && 'message' in err
          ? String((err as { message?: unknown }).message)
          : 'Failed to save edits.';
      setSaveError(message);
    } finally {
      setSaving(false);
    }
  };

  const buttonBase = {
    padding: '8px 14px',
    borderRadius: 8,
    fontSize: 13,
    cursor: 'pointer',
    fontFamily: 'var(--font-sans)',
  } as const;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div
        style={{
          flexShrink: 0,
          padding: '24px 30px 18px',
          borderBottom: '1px solid var(--border)',
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          gap: 16,
        }}
      >
        <div style={{ minWidth: 0 }}>
          <p
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 10,
              letterSpacing: '.14em',
              textTransform: 'uppercase',
              color: 'var(--accent)',
              margin: 0,
              marginBottom: 6,
            }}
          >
            {isEditing ? 'CONSOLIDATED REQUIREMENTS · EDITING' : 'CONSOLIDATED REQUIREMENTS · READY'}
          </p>
          <h1
            style={{
              fontFamily: 'var(--font-display)',
              fontSize: 24,
              fontWeight: 400,
              letterSpacing: '-.02em',
              color: 'var(--fg)',
              margin: 0,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {projectTitle}
          </h1>
        </div>
        <div style={{ display: 'flex', gap: 8, flexShrink: 0, alignItems: 'center' }}>
          <button
            type="button"
            onClick={onBack}
            disabled={isEditing}
            style={{
              ...buttonBase,
              background: 'transparent',
              border: '1px solid var(--border-strong)',
              color: 'var(--fg-dim)',
              opacity: isEditing ? 0.5 : 1,
            }}
          >
            ← Analysis
          </button>

          {isEditing ? (
            <>
              <button
                type="button"
                onClick={handleCancel}
                disabled={saving}
                style={{
                  ...buttonBase,
                  background: 'transparent',
                  border: '1px solid var(--border-strong)',
                  color: 'var(--fg-dim)',
                }}
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleSave}
                disabled={saving}
                style={{
                  ...buttonBase,
                  padding: '8px 16px',
                  background: 'var(--accent)',
                  color: '#1a0a04',
                  border: 'none',
                  fontWeight: 500,
                  boxShadow: 'var(--glow)',
                }}
              >
                {saving ? 'Saving…' : 'Save'}
              </button>
            </>
          ) : (
            <>
              <button
                type="button"
                onClick={handleStartEdit}
                style={{
                  ...buttonBase,
                  background: 'transparent',
                  border: '1px solid var(--border-strong)',
                  color: 'var(--fg-dim)',
                }}
              >
                Edit
              </button>
              <ReportToolbar
                getReportNode={() => reportRef.current}
                markdown={reportContent}
                title={projectTitle}
                trailing={
                  <button
                    type="button"
                    onClick={onOpenChat}
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: 7,
                      padding: '8px 16px',
                      borderRadius: 8,
                      fontSize: 13,
                      fontWeight: 500,
                      background: 'var(--accent)',
                      color: '#1a0a04',
                      border: 'none',
                      boxShadow: 'var(--glow)',
                      cursor: 'pointer',
                      fontFamily: 'var(--font-sans)',
                    }}
                  >
                    Run full pipeline
                    <svg width="13" height="13" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path
                        d="M5 12h14M13 5l7 7-7 7"
                        strokeWidth="2.4"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </svg>
                  </button>
                }
              />
            </>
          )}
        </div>
      </div>

      {saveError && (
        <div
          style={{
            flexShrink: 0,
            padding: '10px 30px',
            background: 'rgba(220, 38, 38, 0.08)',
            color: '#fca5a5',
            fontSize: 13,
            fontFamily: 'var(--font-sans)',
            borderBottom: '1px solid var(--border)',
          }}
        >
          {saveError}
        </div>
      )}

      <div
        style={{
          flex: 1,
          overflowY: 'auto',
          padding: '28px 40px 60px',
          display: 'flex',
          justifyContent: 'center',
        }}
      >
        <div style={{ maxWidth: 820, width: '100%' }}>
          {isEditing ? (
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              spellCheck={false}
              style={{
                width: '100%',
                minHeight: 'calc(100vh - 260px)',
                padding: 18,
                background: 'var(--surface-2)',
                color: 'var(--fg)',
                border: '1px solid var(--border-strong)',
                borderRadius: 10,
                fontFamily: 'var(--font-mono)',
                fontSize: 13,
                lineHeight: 1.55,
                resize: 'vertical',
                outline: 'none',
              }}
            />
          ) : (
            <ReportContent ref={reportRef} content={reportContent} variant="report" />
          )}
        </div>
      </div>
    </div>
  );
}
