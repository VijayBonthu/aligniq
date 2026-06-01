import { useEffect, useMemo, useRef, useState } from 'react';
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
  requireAssumptionAck?: boolean;
}

export default function ReportStep({
  reportContent,
  projectTitle,
  chatHistoryId,
  onOpenChat,
  onBack,
  onContentChange,
  requireAssumptionAck = false,
}: Props) {
  const [assumptionAck, setAssumptionAck] = useState(false);
  const reportRef = useRef<HTMLDivElement | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState(reportContent);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  // Keep draft in sync when parent's reportContent changes (e.g. after regeneration).
  useEffect(() => {
    if (!isEditing) setDraft(reportContent);
  }, [reportContent, isEditing]);

  const today = useMemo(
    () => new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' }),
    [],
  );

  const runLocked = requireAssumptionAck && !assumptionAck;

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

  const ghostBtn = {
    ...buttonBase,
    background: 'transparent',
    border: '1px solid var(--border-strong)',
    color: 'var(--fg-dim)',
  } as const;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* ── Top bar ── */}
      <div
        style={{
          flexShrink: 0,
          padding: '16px clamp(16px, 4vw, 30px)',
          borderBottom: '1px solid var(--border)',
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          gap: 14,
          flexWrap: 'wrap',
          background: 'var(--surface)',
        }}
      >
        <div style={{ minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6, flexWrap: 'wrap' }}>
            <p
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 10,
                letterSpacing: '.14em',
                textTransform: 'uppercase',
                color: 'var(--accent)',
                margin: 0,
              }}
            >
              STEP 4 OF 4 · CONSOLIDATED REQUIREMENTS
            </p>
            {!isEditing && (
              <span
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 5,
                  padding: '2px 9px',
                  borderRadius: 999,
                  background: 'color-mix(in oklab, var(--ok) 12%, transparent)',
                  border: '1px solid color-mix(in oklab, var(--ok) 30%, transparent)',
                }}
              >
                <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--ok)' }} />
                <span
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: 9,
                    letterSpacing: '.08em',
                    textTransform: 'uppercase',
                    color: 'var(--ok)',
                  }}
                >
                  Ready
                </span>
              </span>
            )}
          </div>
          <h1
            style={{
              fontFamily: 'var(--font-display)',
              fontSize: 22,
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
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', justifyContent: 'flex-end' }}>
          <button type="button" onClick={onBack} disabled={isEditing} style={{ ...ghostBtn, opacity: isEditing ? 0.5 : 1 }}>
            ← Analysis
          </button>

          {isEditing ? (
            <>
              <button type="button" onClick={handleCancel} disabled={saving} style={ghostBtn}>
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
                  color: 'var(--accent-ink)',
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
              <button type="button" onClick={handleStartEdit} style={ghostBtn}>
                Edit
              </button>
              <ReportToolbar
                getReportNode={() => reportRef.current}
                markdown={reportContent}
                title={projectTitle}
                trailing={<RunButton onClick={onOpenChat} locked={runLocked} />}
              />
            </>
          )}
        </div>
      </div>

      {saveError && (
        <div
          style={{
            flexShrink: 0,
            padding: '10px clamp(16px, 4vw, 30px)',
            background: 'color-mix(in oklab, var(--danger) 10%, transparent)',
            color: 'var(--danger)',
            fontSize: 13,
            fontFamily: 'var(--font-sans)',
            borderBottom: '1px solid var(--border)',
          }}
        >
          {saveError}
        </div>
      )}

      {requireAssumptionAck && !isEditing && (
        <label
          style={{
            flexShrink: 0,
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            padding: '11px clamp(16px, 4vw, 30px)',
            background: 'color-mix(in oklab, var(--warn) 9%, transparent)',
            color: 'var(--warn)',
            fontSize: 13,
            fontFamily: 'var(--font-sans)',
            borderBottom: '1px solid var(--border)',
            cursor: 'pointer',
          }}
        >
          <input
            type="checkbox"
            checked={assumptionAck}
            onChange={(e) => setAssumptionAck(e.target.checked)}
            style={{ accentColor: 'var(--warn)', cursor: 'pointer' }}
          />
          I&rsquo;ve reviewed the AI-inferred assumptions before running the full pipeline.
        </label>
      )}

      {/* ── Document ── */}
      <div
        style={{
          flex: 1,
          overflowY: 'auto',
          padding: 'clamp(18px, 4vw, 32px) clamp(14px, 4vw, 40px) 60px',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: 18,
        }}
      >
        <div
          style={{
            maxWidth: 860,
            width: '100%',
            background: 'var(--surface)',
            border: '1px solid var(--border)',
            borderRadius: 16,
            boxShadow: 'var(--shadow-card)',
            padding: isEditing
              ? 'clamp(18px, 4vw, 24px) clamp(16px, 4vw, 28px)'
              : 'clamp(24px, 5vw, 44px) clamp(18px, 5vw, 52px)',
          }}
        >
          {/* Cover masthead */}
          <div style={{ borderBottom: '1px solid var(--border)', paddingBottom: 20, marginBottom: 28 }}>
            <p
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 10,
                letterSpacing: '.18em',
                textTransform: 'uppercase',
                color: 'var(--accent)',
                margin: '0 0 10px',
              }}
            >
              Consolidated Requirements Brief
            </p>
            <h2
              style={{
                fontFamily: 'var(--font-display)',
                fontSize: 'clamp(23px, 5vw, 30px)',
                fontWeight: 400,
                letterSpacing: '-.02em',
                color: 'var(--fg)',
                margin: '0 0 12px',
                lineHeight: 1.15,
              }}
            >
              {projectTitle}
            </h2>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                flexWrap: 'wrap',
                fontFamily: 'var(--font-mono)',
                fontSize: 11,
                color: 'var(--fg-muted)',
              }}
            >
              <span>GroundedIQ</span>
              <Dot />
              <span>{today}</span>
              <Dot />
              <span>Scope of record · pre-build</span>
            </div>
          </div>

          {isEditing ? (
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              spellCheck={false}
              style={{
                width: '100%',
                minHeight: 'calc(100vh - 320px)',
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

        {/* Sign-off / next step */}
        {!isEditing && (
          <div
            style={{
              maxWidth: 860,
              width: '100%',
              padding: '20px 24px',
              borderRadius: 14,
              background: 'var(--surface)',
              border: '1px solid var(--border)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 20,
              flexWrap: 'wrap',
            }}
          >
            <div style={{ display: 'flex', gap: 13, alignItems: 'flex-start', flex: 1, minWidth: 260 }}>
              <div
                style={{
                  flexShrink: 0,
                  width: 36,
                  height: 36,
                  borderRadius: 10,
                  background: 'var(--accent-soft)',
                  border: '1px solid color-mix(in oklab, var(--accent) 30%, transparent)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                <svg width="18" height="18" fill="none" stroke="var(--accent)" viewBox="0 0 24 24">
                  <path d="M9 11l3 3L22 4" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                  <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </div>
              <div>
                <p style={{ fontSize: 14, fontWeight: 600, color: 'var(--fg)', margin: '0 0 3px' }}>
                  This brief is your scope of record
                </p>
                <p style={{ fontSize: 12.5, color: 'var(--fg-muted)', lineHeight: 1.55, margin: 0, maxWidth: 540 }}>
                  Edit anything above until it reflects the engagement, or export it to share. When you&rsquo;re
                  happy, run the full pipeline to produce the complete technical report — architecture,
                  estimates, team plan, risks, and diagrams.
                </p>
              </div>
            </div>
            <RunButton onClick={onOpenChat} locked={runLocked} large />
          </div>
        )}
      </div>
    </div>
  );
}

function Dot() {
  return <span style={{ width: 3, height: 3, borderRadius: '50%', background: 'var(--fg-muted)', display: 'inline-block' }} />;
}

function RunButton({
  onClick,
  locked,
  large,
}: {
  onClick: () => void;
  locked?: boolean;
  large?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={locked}
      title={locked ? 'Acknowledge the AI-inferred assumptions before running the full pipeline.' : undefined}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 7,
        padding: large ? '11px 20px' : '8px 16px',
        borderRadius: large ? 10 : 8,
        fontSize: large ? 14 : 13,
        fontWeight: 500,
        background: 'var(--accent)',
        color: 'var(--accent-ink)',
        border: 'none',
        boxShadow: 'var(--glow)',
        cursor: locked ? 'not-allowed' : 'pointer',
        opacity: locked ? 0.55 : 1,
        fontFamily: large ? 'var(--font-display)' : 'var(--font-sans)',
        whiteSpace: 'nowrap',
        flexShrink: 0,
      }}
    >
      Run full pipeline
      <svg width="13" height="13" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path d="M5 12h14M13 5l7 7-7 7" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </button>
  );
}
