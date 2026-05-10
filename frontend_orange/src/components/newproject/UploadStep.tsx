import { useEffect, useRef, useState } from 'react';
import { toast } from 'react-hot-toast';
import { uploadFiles, type UploadPresalesResponse } from '../../services/uploadService';
import ProcessingSteps from './ProcessingSteps';

interface UploadStepProps {
  onComplete: (response: UploadPresalesResponse) => void;
  onBeforeUpload?: () => boolean;
}

const ACCEPTED = '.pdf,.docx,.pptx,.txt,.md,.markdown,.mdx,.csv';

export default function UploadStep({ onComplete, onBeforeUpload }: UploadStepProps) {
  const [file, setFile] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [procStep, setProcStep] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

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

  const handleAnalyse = async () => {
    if (!file) return;
    if (onBeforeUpload && !onBeforeUpload()) return;
    setProcessing(true);
    setProcStep(0);
    try {
      const res = await uploadFiles([file], 'presales');
      if (!('presales_id' in res) || !res.presales_id) {
        toast.error('Upload returned an unexpected response.');
        setProcessing(false);
        return;
      }
      onComplete(res);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Upload failed';
      toast.error(msg);
      setProcessing(false);
      setProcStep(0);
    }
  };

  return (
    <div style={{ maxWidth: 580, margin: '0 auto', padding: '48px 24px' }}>
      <div style={{ textAlign: 'center', marginBottom: 32 }}>
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
          Upload your project brief
        </h1>
        <p style={{ fontSize: 14, color: 'var(--fg-dim)', lineHeight: 1.6 }}>
          AlignIQ will scan it for ambiguities, risks, and critical unknowns in under 2 minutes.
        </p>
      </div>

      {!processing ? (
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
                dragOver ? 'var(--accent)' : file ? 'rgba(122,229,130,.4)' : 'var(--border-strong)'
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
                    background: 'rgba(122,229,130,.14)',
                    border: '1px solid rgba(122,229,130,.3)',
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
                onClick={handleAnalyse}
                style={{
                  minWidth: 220,
                  padding: '11px 20px',
                  borderRadius: 10,
                  border: 'none',
                  background: 'var(--accent)',
                  color: '#1a0a04',
                  fontFamily: 'var(--font-display)',
                  fontSize: 14,
                  fontWeight: 500,
                  cursor: 'pointer',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 8,
                  justifyContent: 'center',
                }}
              >
                Analyse document →
              </button>
            </div>
          )}
        </>
      ) : (
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
            Processing {file?.name}…
          </p>
          <ProcessingSteps step={procStep} />
        </div>
      )}
    </div>
  );
}
