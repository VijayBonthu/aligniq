import { useEffect, useRef, useState } from 'react';
import { toast } from 'react-hot-toast';
import { isAxiosError } from 'axios';
import { uploadFiles, type UploadPresalesResponse } from '../../services/uploadService';
import { buildBriefDocx } from '../../utils/buildBriefDocx';
import ProcessingSteps from './ProcessingSteps';
import BriefComposer, { EMPTY_DRAFT, type DraftState } from './BriefComposer';

interface RejectionDetail {
  rejection_reason?: string;
  next_step?: string;
  classification?: {
    document_type?: string;
    confidence?: number;
  };
}

interface UploadStepProps {
  onComplete: (response: UploadPresalesResponse) => void;
  onBeforeUpload?: () => boolean;
}

type Mode = 'upload' | 'write';

const ACCEPTED = '.pdf,.docx,.pptx,.txt,.md,.markdown,.mdx,.csv';

export default function UploadStep({ onComplete, onBeforeUpload }: UploadStepProps) {
  const [mode, setMode] = useState<Mode>('upload');
  const [file, setFile] = useState<File | null>(null);
  const [draft, setDraft] = useState<DraftState>(EMPTY_DRAFT);
  const [dragOver, setDragOver] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [processingLabel, setProcessingLabel] = useState('');
  const [procStep, setProcStep] = useState(0);
  const [rejection, setRejection] = useState<RejectionDetail | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // After a "not an RFP" rejection: in write mode just dismiss the card so the
  // user can refine the draft they still have; in upload mode reopen the picker.
  const resetForNewFile = () => {
    setRejection(null);
    if (mode === 'write') return;
    setFile(null);
    if (inputRef.current) inputRef.current.value = '';
    inputRef.current?.click();
  };

  // Animate the 5-stage indicator while the API call is in flight.
  // The API resolution is the source of truth; this is purely visual.
  useEffect(() => {
    if (!processing) return;
    if (procStep >= 4) return;
    const t = setTimeout(() => setProcStep((s) => s + 1), 1400);
    return () => clearTimeout(t);
  }, [processing, procStep]);

  const handleFiles = (files: FileList | File[] | null) => {
    if (!files || files.length === 0) return;
    setFile(files[0]);
  };

  // Single upload routine shared by both the file path and the typed-brief path.
  // The typed brief is packaged as a .docx (see buildBriefDocx) so it rides the
  // exact same /upload + presales pipeline — including vision summaries of any
  // embedded screenshots — with no backend change.
  const runUpload = async (toUpload: File, label: string) => {
    if (onBeforeUpload && !onBeforeUpload()) return;
    setRejection(null);
    setProcessingLabel(label);
    setProcessing(true);
    setProcStep(0);
    try {
      const res = await uploadFiles([toUpload], 'presales');
      if (!('presales_id' in res) || !res.presales_id) {
        toast.error('Upload returned an unexpected response.');
        setProcessing(false);
        return;
      }
      onComplete(res);
    } catch (err: unknown) {
      // Pre-flight classifier rejection (HTTP 422) — show a dedicated card instead of a toast,
      // since the user needs to understand *why* and refine their input.
      if (isAxiosError(err) && err.response?.status === 422) {
        const detail = (err.response.data as { detail?: RejectionDetail | string })?.detail;
        if (detail && typeof detail === 'object' && (detail.rejection_reason || detail.next_step)) {
          setRejection(detail);
          setProcessing(false);
          setProcStep(0);
          return;
        }
      }
      const msg = err instanceof Error ? err.message : 'Upload failed';
      toast.error(msg);
      setProcessing(false);
      setProcStep(0);
    }
  };

  const handleAnalyseFile = () => {
    if (!file) return;
    void runUpload(file, file.name);
  };

  const handleSubmitBrief = async () => {
    try {
      const docx = await buildBriefDocx({
        title: draft.title,
        body: draft.body,
        screenshots: draft.screenshots.map(({ dataUrl, width, height, caption }) => ({
          dataUrl,
          width,
          height,
          caption,
        })),
      });
      await runUpload(docx, draft.title.trim() || 'your brief');
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Could not package the brief.';
      toast.error(msg);
      setProcessing(false);
      setProcStep(0);
    }
  };

  const maxW = processing ? 640 : mode === 'write' ? 920 : 620;

  return (
    <div style={{ maxWidth: maxW, margin: '0 auto', padding: 'clamp(28px, 5vw, 44px) clamp(16px, 4vw, 24px)', transition: 'max-width .2s' }}>
      <div style={{ textAlign: 'center', marginBottom: 28 }}>
        <p
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 10,
            letterSpacing: '.14em',
            textTransform: 'uppercase',
            color: 'var(--accent)',
            marginBottom: 8,
          }}
        >
          STEP 1 OF 4
        </p>
        <h1
          style={{
            fontFamily: 'var(--font-display)',
            fontSize: 32,
            fontWeight: 400,
            letterSpacing: '-.02em',
            color: 'var(--fg)',
            marginBottom: 10,
          }}
        >
          Add your project brief
        </h1>
        <p style={{ fontSize: 14, color: 'var(--fg-dim)', lineHeight: 1.6, maxWidth: 540, margin: '0 auto' }}>
          Upload a document — or write it out here. GroundedIQ scans it for ambiguities, risks, and
          critical unknowns in under 2 minutes.
        </p>
      </div>

      {rejection && (
        <div
          style={{
            marginBottom: 20,
            padding: 18,
            borderRadius: 12,
            background: 'rgba(234, 179, 8, 0.06)',
            border: '1px solid rgba(234, 179, 8, 0.35)',
          }}
        >
          <p
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 10,
              letterSpacing: '.14em',
              textTransform: 'uppercase',
              color: 'var(--warn)',
              marginBottom: 8,
            }}
          >
            Doesn&rsquo;t look like an RFP
          </p>
          {rejection.rejection_reason && (
            <p style={{ fontSize: 14, color: 'var(--fg)', lineHeight: 1.55, marginBottom: 8 }}>
              {rejection.rejection_reason}
            </p>
          )}
          {rejection.next_step && (
            <p style={{ fontSize: 13, color: 'var(--fg-dim)', lineHeight: 1.55, marginBottom: 14 }}>
              {rejection.next_step}
            </p>
          )}
          {rejection.classification?.document_type && (
            <p
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 11,
                color: 'var(--fg-muted)',
                marginBottom: 14,
              }}
            >
              Detected: {rejection.classification.document_type}
              {typeof rejection.classification.confidence === 'number'
                ? ` (${Math.round(rejection.classification.confidence * 100)}% confidence)`
                : ''}
            </p>
          )}
          <button
            type="button"
            onClick={resetForNewFile}
            style={{
              padding: '8px 14px',
              background: 'var(--accent)',
              color: 'var(--accent-ink)',
              border: 'none',
              borderRadius: 8,
              fontSize: 13,
              fontWeight: 500,
              cursor: 'pointer',
              fontFamily: 'var(--font-sans)',
            }}
          >
            Choose a different file
          </button>
        </div>
      )}

      {processing ? (
        <div
          style={{
            background: 'var(--surface)',
            border: '1px solid var(--border)',
            borderRadius: 14,
            padding: '24px 28px',
          }}
        >
          <p
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 10,
              color: 'var(--accent)',
              letterSpacing: '.1em',
              textTransform: 'uppercase',
              marginBottom: 4,
            }}
          >
            PRESALES ANALYSIS PIPELINE
          </p>
          <p style={{ fontSize: 13, color: 'var(--fg-muted)', marginBottom: 16 }}>
            Processing {processingLabel}…
          </p>
          <ProcessingSteps step={procStep} />
        </div>
      ) : (
        <>
          {/* Mode toggle */}
          <div
            style={{
              display: 'flex',
              gap: 4,
              padding: 4,
              background: 'var(--surface)',
              border: '1px solid var(--border)',
              borderRadius: 999,
              width: 'fit-content',
              margin: '0 auto 24px',
            }}
          >
            {(['upload', 'write'] as Mode[]).map((m) => {
              const active = mode === m;
              return (
                <button
                  key={m}
                  type="button"
                  onClick={() => setMode(m)}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 7,
                    padding: '8px 16px',
                    borderRadius: 999,
                    border: 'none',
                    background: active ? 'var(--accent)' : 'transparent',
                    color: active ? 'var(--accent-ink)' : 'var(--fg-dim)',
                    fontSize: 13,
                    fontWeight: 500,
                    cursor: 'pointer',
                    transition: 'all .15s',
                    fontFamily: 'var(--font-sans)',
                  }}
                >
                  {m === 'upload' ? (
                    <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" strokeWidth="1.8" strokeLinecap="round" />
                      <polyline points="17 8 12 3 7 8" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                      <line x1="12" y1="3" x2="12" y2="15" strokeWidth="1.8" strokeLinecap="round" />
                    </svg>
                  ) : (
                    <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path d="M12 20h9" strokeWidth="1.8" strokeLinecap="round" />
                      <path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4z" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  )}
                  {m === 'upload' ? 'Upload a document' : 'Write it out'}
                </button>
              );
            })}
          </div>

          {mode === 'upload' ? (
            <>
              <label
                htmlFor="np-file-input"
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragOver(true);
                }}
                onDragLeave={() => setDragOver(false)}
                onDrop={(e) => {
                  e.preventDefault();
                  setDragOver(false);
                  handleFiles(e.dataTransfer.files);
                }}
                style={{
                  display: 'block',
                  padding: '40px 24px',
                  borderRadius: 14,
                  background: dragOver ? 'var(--accent-soft)' : 'var(--surface)',
                  border: `1.5px dashed ${
                    dragOver ? 'var(--accent)' : file ? 'rgba(126,168,137,.4)' : 'var(--border-strong)'
                  }`,
                  textAlign: 'center',
                  cursor: 'pointer',
                  transition: 'all .2s',
                }}
              >
                <input
                  ref={inputRef}
                  id="np-file-input"
                  type="file"
                  accept={ACCEPTED}
                  onChange={(e) => handleFiles(e.target.files)}
                  style={{ display: 'none' }}
                />
                {file ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    <div
                      style={{
                        width: 44,
                        height: 44,
                        margin: '0 auto',
                        borderRadius: 10,
                        background: 'rgba(126,168,137,.14)',
                        border: '1px solid rgba(126,168,137,.3)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                      }}
                    >
                      <svg width="20" height="20" fill="none" stroke="var(--ok)" viewBox="0 0 24 24">
                        <polyline points="20 6 9 17 4 12" strokeWidth="2.5" strokeLinecap="round" />
                      </svg>
                    </div>
                    <p style={{ fontSize: 14, color: 'var(--fg)', fontWeight: 500 }}>{file.name}</p>
                    <p style={{ fontSize: 11, color: 'var(--fg-muted)' }}>
                      {(file.size / 1024).toFixed(1)} KB · click to replace
                    </p>
                  </div>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                    <div
                      style={{
                        width: 44,
                        height: 44,
                        margin: '0 auto',
                        borderRadius: 10,
                        background: 'var(--surface-2)',
                        border: '1px solid var(--border)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                      }}
                    >
                      <svg width="18" height="18" fill="none" stroke="var(--accent)" viewBox="0 0 24 24">
                        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" strokeWidth="1.8" strokeLinecap="round" />
                        <polyline points="17 8 12 3 7 8" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                        <line x1="12" y1="3" x2="12" y2="15" strokeWidth="1.8" strokeLinecap="round" />
                      </svg>
                    </div>
                    <p style={{ fontSize: 14, color: 'var(--fg)' }}>
                      Drop your brief here, or <span style={{ color: 'var(--accent)' }}>browse</span>
                    </p>
                    <p
                      style={{
                        fontFamily: 'var(--font-mono)',
                        fontSize: 10,
                        color: 'var(--fg-muted)',
                        letterSpacing: '.1em',
                        textTransform: 'uppercase',
                      }}
                    >
                      PDF · DOCX · PPTX · TXT · MD · CSV
                    </p>
                  </div>
                )}
              </label>

              {file && (
                <div style={{ marginTop: 24, textAlign: 'center' }}>
                  <button
                    type="button"
                    onClick={handleAnalyseFile}
                    style={{
                      minWidth: 220,
                      padding: '11px 20px',
                      borderRadius: 10,
                      border: 'none',
                      background: 'var(--accent)',
                      color: 'var(--accent-ink)',
                      fontFamily: 'var(--font-display)',
                      fontSize: 14,
                      fontWeight: 500,
                      cursor: 'pointer',
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: 8,
                      justifyContent: 'center',
                      boxShadow: 'var(--glow)',
                    }}
                  >
                    Analyse document →
                  </button>
                </div>
              )}
            </>
          ) : (
            <BriefComposer
              draft={draft}
              setDraft={setDraft}
              submitting={processing}
              onSubmit={handleSubmitBrief}
            />
          )}
        </>
      )}
    </div>
  );
}
