import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import {
  getSections,
  polishSection,
  revertPolish,
  updateConfig,
} from '../services/deliverableService';
import type {
  CustomSection,
  DeliverableConfig,
  DeliverableSection,
  PolishedSection,
} from '../types/deliverable';
import SectionRow from '../components/deliverable/SectionRow';
import CustomSectionRow from '../components/deliverable/CustomSectionRow';
import AddSectionButton from '../components/deliverable/AddSectionButton';
import PreviewPane, { buildAssembledMarkdown } from '../components/deliverable/PreviewPane';
import { exportMarkdownToPdf, buildPdfBlob } from '../utils/exportPdf';
import { exportMarkdownToDocx, buildDocxBlob } from '../utils/exportDocx';
import useMediaQuery from '../hooks/useMediaQuery';
import JiraSendPanel from '../components/deliverable/JiraSendPanel';

function emptyConfig(): DeliverableConfig {
  return {
    included_section_ids: [],
    excluded_section_ids: [],
    section_edits: {},
    custom_sections: [],
  };
}

export default function DeliverableBuilder() {
  const { chatHistoryId } = useParams<{ chatHistoryId: string }>();
  const navigate = useNavigate();

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['deliverable-sections', chatHistoryId],
    queryFn: () => getSections(chatHistoryId!),
    enabled: !!chatHistoryId,
  });

  const [excluded, setExcluded] = useState<Set<string>>(new Set());
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [customSections, setCustomSections] = useState<CustomSection[]>([]);
  const [polished, setPolished] = useState<Record<string, PolishedSection>>({});
  const [polishing, setPolishing] = useState<Set<string>>(new Set());
  const [exporting, setExporting] = useState<'pdf' | 'docx' | null>(null);
  const [jiraOpen, setJiraOpen] = useState(false);
  const previewRef = useRef<HTMLDivElement | null>(null);
  const persistTimer = useRef<number | null>(null);
  // Tablet/phone: the 384px curate panel + preview can't sit side-by-side, so we
  // show one at a time behind a Curate | Preview toggle (both stay mounted so the
  // preview DOM is available for PDF/diagram export).
  const stacked = useMediaQuery('(max-width: 1024px)');
  const [pane, setPane] = useState<'curate' | 'preview'>('curate');

  // Hydrate state from server response. Done once per query result; subsequent
  // user interactions own the local state (then persist back via PUT).
  useEffect(() => {
    if (!data) return;
    const cfg = data.config;
    if (cfg) {
      setExcluded(new Set(cfg.excluded_section_ids ?? []));
      setEdits(cfg.section_edits ?? {});
      setCustomSections(cfg.custom_sections ?? []);
    } else {
      setExcluded(new Set(data.default_excluded_ids ?? []));
      setEdits({});
      setCustomSections([]);
    }
    setPolished(data.polished_sections ?? {});
  }, [data]);

  const sections = data?.sections ?? [];
  const includedIds = useMemo(() => sections.filter((s) => !excluded.has(s.id)).map((s) => s.id), [
    sections,
    excluded,
  ]);

  // Debounced persistence — every state mutation re-arms the timer.
  const persistConfig = (next?: Partial<DeliverableConfig>) => {
    if (!chatHistoryId) return;
    if (persistTimer.current) window.clearTimeout(persistTimer.current);
    const config: DeliverableConfig = {
      included_section_ids: next?.included_section_ids ?? includedIds,
      excluded_section_ids: next?.excluded_section_ids ?? Array.from(excluded),
      section_edits: next?.section_edits ?? edits,
      custom_sections: next?.custom_sections ?? customSections,
    };
    persistTimer.current = window.setTimeout(() => {
      updateConfig(chatHistoryId, config).catch((err) => {
        toast.error(err?.response?.data?.detail || 'Failed to save curation');
      });
    }, 600);
  };

  const onToggleInclude = (id: string, include: boolean) => {
    setExcluded((prev) => {
      const next = new Set(prev);
      if (include) next.delete(id);
      else next.add(id);
      const newIncluded = sections.filter((s) => !next.has(s.id)).map((s) => s.id);
      persistConfig({
        excluded_section_ids: Array.from(next),
        included_section_ids: newIncluded,
      });
      return next;
    });
  };

  const onSaveEdit = (id: string, markdown: string) => {
    setEdits((prev) => {
      const next = { ...prev, [id]: markdown };
      persistConfig({ section_edits: next });
      return next;
    });
  };

  const onPolish = async (id: string) => {
    if (!chatHistoryId) return;
    setPolishing((prev) => new Set(prev).add(id));
    try {
      const res = await polishSection(chatHistoryId, id);
      setPolished((prev) => ({
        ...prev,
        [id]: { markdown: res.polished_markdown, polished_at: new Date().toISOString() },
      }));
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Polish failed');
    } finally {
      setPolishing((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    }
  };

  const onRevertPolish = async (id: string) => {
    if (!chatHistoryId) return;
    try {
      await revertPolish(chatHistoryId, id);
      setPolished((prev) => {
        const next = { ...prev };
        delete next[id];
        return next;
      });
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Revert failed');
    }
  };

  const onAddCustom = (cs: CustomSection) => {
    setCustomSections((prev) => {
      const next = [...prev, cs];
      persistConfig({ custom_sections: next });
      return next;
    });
  };

  const onChangeCustom = (next: CustomSection) => {
    setCustomSections((prev) => {
      const out = prev.map((c) => (c.id === next.id ? next : c));
      persistConfig({ custom_sections: out });
      return out;
    });
  };

  const onDeleteCustom = (id: string) => {
    setCustomSections((prev) => {
      const out = prev.filter((c) => c.id !== id);
      persistConfig({ custom_sections: out });
      return out;
    });
  };

  const downloadFilename = useMemo(() => {
    const stamp = new Date().toISOString().slice(0, 10);
    return `deliverable-${stamp}`;
  }, []);

  // Diagram rasterization reads getBoundingClientRect, which is 0 while the
  // preview is display:none (stacked + curate pane). Reveal it before exporting.
  const ensurePreviewVisible = async () => {
    if (stacked && pane !== 'preview') {
      setPane('preview');
      await new Promise((r) => setTimeout(r, 350));
    }
  };

  // Shared prep: reveal the preview (diagrams need layout) and wait for in-flight mermaid
  // renders so every diagram is captured. Returns the assembled markdown + the preview node.
  const prepareMarkdown = async (): Promise<{ md: string; node: HTMLElement | null }> => {
    await ensurePreviewVisible();
    const node = previewRef.current;
    for (let i = 0; node && i < 60 && node.querySelectorAll('.diagram-block--loading').length; i++) {
      await new Promise((r) => setTimeout(r, 100));
    }
    const md = buildAssembledMarkdown({
      sections,
      excludedIds: excluded,
      sectionEdits: edits,
      polished,
      customSections,
    });
    return { md, node };
  };

  // Used by the "Send to Jira" panel — same curated content as the downloads, as a Blob.
  const buildDeliverableBlob = async (fmt: 'pdf' | 'docx'): Promise<{ blob: Blob; filename: string }> => {
    const { md, node } = await prepareMarkdown();
    if (fmt === 'pdf') {
      return { blob: await buildPdfBlob(md, { title: 'Project Deliverable', node }), filename: `${downloadFilename}.pdf` };
    }
    return { blob: await buildDocxBlob(md, { title: 'Project Deliverable', node }), filename: `${downloadFilename}.docx` };
  };

  const onDownloadPdf = async () => {
    setExporting('pdf');
    try {
      const { md, node } = await prepareMarkdown();
      await exportMarkdownToPdf(md, `${downloadFilename}.pdf`, { title: 'Project Deliverable', node });
    } catch (err: any) {
      toast.error(err?.message || 'PDF export failed');
    } finally {
      setExporting(null);
    }
  };

  const onDownloadDocx = async () => {
    setExporting('docx');
    try {
      const { md, node } = await prepareMarkdown();
      await exportMarkdownToDocx(md, `${downloadFilename}.docx`, { title: 'Project Deliverable', node });
    } catch (err: any) {
      toast.error(err?.message || 'DOCX export failed');
    } finally {
      setExporting(null);
    }
  };

  if (isError) {
    return (
      <div style={{ padding: 32, color: 'var(--fg-muted)' }}>
        Could not load this report.{' '}
        <button onClick={() => refetch()} style={{ color: 'var(--accent)' }}>
          Retry
        </button>
      </div>
    );
  }

  if (isLoading || !data) {
    return (
      <div style={{ padding: 32, color: 'var(--fg-muted)', fontFamily: 'var(--font-mono)' }}>
        Loading sections…
      </div>
    );
  }

  const standardAnchors = sections.filter((s) => !excluded.has(s.id));

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      <div
        style={{
          flexShrink: 0,
          minHeight: 56,
          borderBottom: '1px solid var(--border)',
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          padding: '8px clamp(10px, 3vw, 16px)',
          background: 'var(--surface)',
        }}
      >
        <button
          onClick={() => navigate(`/chat/${chatHistoryId}`)}
          style={{
            background: 'none',
            border: 'none',
            color: 'var(--fg-muted)',
            display: 'flex',
            alignItems: 'center',
            gap: 5,
            fontSize: 13,
            cursor: 'pointer',
            padding: '4px 6px',
            borderRadius: 6,
            fontFamily: 'var(--font-sans)',
          }}
        >
          <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path d="M15 18l-6-6 6-6" strokeWidth="2" strokeLinecap="round" />
          </svg>
          Chat
        </button>
        <div style={{ width: 1, height: 18, background: 'var(--border)' }} />
        <div
          style={{
            flex: 1,
            minWidth: 0,
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'center',
          }}
        >
          <span style={{ fontSize: 13.5, fontWeight: 500, color: 'var(--fg)', fontFamily: 'var(--font-sans)' }}>
            Deliverable Builder
          </span>
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 9,
              letterSpacing: '.14em',
              textTransform: 'uppercase',
              color: 'var(--fg-muted)',
              marginTop: 1,
            }}
          >
            Client deliverable · curate · export
          </span>
        </div>
        <button
          onClick={onDownloadDocx}
          disabled={exporting !== null}
          style={headerBtn()}
        >
          {exporting === 'docx' ? 'Building…' : stacked ? 'DOCX' : 'Download DOCX'}
        </button>
        <button
          onClick={onDownloadPdf}
          disabled={exporting !== null}
          style={headerBtn()}
        >
          {exporting === 'pdf' ? 'Building…' : stacked ? 'PDF' : 'Download PDF'}
        </button>
        <button
          onClick={() => setJiraOpen(true)}
          disabled={exporting !== null}
          style={headerBtn(true)}
        >
          {stacked ? 'Jira' : 'Send to Jira'}
        </button>
      </div>

      {stacked && (
        <div
          style={{
            flexShrink: 0,
            display: 'flex',
            gap: 4,
            padding: 4,
            margin: '10px auto 0',
            background: 'var(--surface)',
            border: '1px solid var(--border)',
            borderRadius: 999,
            width: 'fit-content',
          }}
        >
          {(['curate', 'preview'] as const).map((p) => (
            <button
              key={p}
              onClick={() => setPane(p)}
              style={{
                padding: '7px 18px',
                borderRadius: 999,
                border: 'none',
                background: pane === p ? 'var(--accent)' : 'transparent',
                color: pane === p ? 'var(--accent-ink)' : 'var(--fg-dim)',
                fontSize: 12.5,
                fontWeight: 500,
                cursor: 'pointer',
                fontFamily: 'var(--font-sans)',
                textTransform: 'capitalize',
              }}
            >
              {p}
            </button>
          ))}
        </div>
      )}

      <SectionStructureBanner sections={sections} hasConfig={!!data.config} />

      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        <aside
          style={{
            width: stacked ? '100%' : 384,
            flexShrink: 0,
            borderRight: stacked ? 'none' : '1px solid var(--border)',
            overflowY: 'auto',
            background: 'var(--surface)',
            display: stacked && pane !== 'curate' ? 'none' : 'block',
          }}
        >
          {sections.map((s) => (
            <SectionRow
              key={s.id}
              section={s}
              included={!excluded.has(s.id)}
              edited={edits[s.id] ?? null}
              polished={polished[s.id] ?? null}
              polishing={polishing.has(s.id)}
              onToggleInclude={onToggleInclude}
              onSaveEdit={onSaveEdit}
              onPolish={onPolish}
              onRevertPolish={onRevertPolish}
            />
          ))}
          {customSections.map((cs) => (
            <CustomSectionRow
              key={cs.id}
              custom={cs}
              anchorOptions={standardAnchors}
              onChange={onChangeCustom}
              onDelete={onDeleteCustom}
            />
          ))}
          <AddSectionButton anchorOptions={standardAnchors} onAdd={onAddCustom} />
        </aside>
        <main
          style={{
            flex: 1,
            overflowY: 'auto',
            background: 'var(--surface-2)',
            display: stacked && pane !== 'preview' ? 'none' : 'block',
          }}
        >
          <PreviewPane
            ref={previewRef}
            sections={sections}
            excludedIds={excluded}
            sectionEdits={edits}
            polished={polished}
            customSections={customSections}
          />
        </main>
      </div>

      <JiraSendPanel
        open={jiraOpen}
        onClose={() => setJiraOpen(false)}
        defaultTitle="Project Deliverable"
        buildBlob={buildDeliverableBlob}
      />
    </div>
  );
}

function SectionStructureBanner({
  sections,
  hasConfig,
}: {
  sections: DeliverableSection[];
  hasConfig: boolean;
}) {
  if (sections.length === 0 || hasConfig) return null;
  return (
    <div
      style={{
        flexShrink: 0,
        padding: '8px 18px',
        background: 'var(--accent-soft)',
        color: 'var(--accent)',
        fontSize: 12,
        fontFamily: 'var(--font-mono)',
        letterSpacing: '.04em',
        borderBottom: '1px solid var(--border)',
      }}
    >
      Defaults applied: internal sections (open questions, alternatives, staffing) are
      unchecked. Toggle anything you want included.
    </div>
  );
}

function headerBtn(primary = false): React.CSSProperties {
  return {
    fontSize: 10.5,
    fontFamily: 'var(--font-mono)',
    letterSpacing: '.1em',
    textTransform: 'uppercase',
    padding: '7px 14px',
    borderRadius: 999,
    border: `1px solid ${primary ? 'var(--accent)' : 'var(--border-strong)'}`,
    background: primary ? 'var(--accent)' : 'var(--surface-2)',
    color: primary ? 'var(--accent-ink)' : 'var(--fg-dim)',
    cursor: 'pointer',
  };
}
