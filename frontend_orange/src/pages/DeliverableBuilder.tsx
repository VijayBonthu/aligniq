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
import { exportNodeToPdf } from '../utils/exportPdf';
import { exportMarkdownToDocx } from '../utils/exportDocx';

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
  const previewRef = useRef<HTMLDivElement | null>(null);
  const persistTimer = useRef<number | null>(null);

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

  const onDownloadPdf = async () => {
    if (!previewRef.current) return;
    setExporting('pdf');
    try {
      await exportNodeToPdf(previewRef.current, `${downloadFilename}.pdf`, {
        title: 'Project Deliverable',
      });
    } catch (err: any) {
      toast.error(err?.message || 'PDF export failed');
    } finally {
      setExporting(null);
    }
  };

  const onDownloadDocx = async () => {
    setExporting('docx');
    try {
      const md = buildAssembledMarkdown({
        sections,
        excludedIds: excluded,
        sectionEdits: edits,
        polished,
        customSections,
      });
      await exportMarkdownToDocx(md, `${downloadFilename}.docx`, { title: 'Project Deliverable' });
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
          height: 50,
          borderBottom: '1px solid var(--border)',
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          padding: '0 18px',
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
        <span
          style={{
            fontSize: 13.5,
            fontWeight: 500,
            color: 'var(--fg)',
            flex: 1,
            fontFamily: 'var(--font-sans)',
          }}
        >
          Deliverable Builder
        </span>
        <button
          onClick={onDownloadDocx}
          disabled={exporting !== null}
          style={headerBtn()}
        >
          {exporting === 'docx' ? 'Building…' : 'Download DOCX'}
        </button>
        <button
          onClick={onDownloadPdf}
          disabled={exporting !== null}
          style={headerBtn(true)}
        >
          {exporting === 'pdf' ? 'Building…' : 'Download PDF'}
        </button>
      </div>

      <SectionStructureBanner sections={sections} hasConfig={!!data.config} />

      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        <aside
          style={{
            width: 420,
            flexShrink: 0,
            borderRight: '1px solid var(--border)',
            overflowY: 'auto',
            background: 'var(--surface)',
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
        <main style={{ flex: 1, overflowY: 'auto', background: 'var(--surface-2)' }}>
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
    fontSize: 11,
    fontFamily: 'var(--font-mono)',
    letterSpacing: '.06em',
    padding: '5px 12px',
    borderRadius: 6,
    border: `1px solid ${primary ? 'var(--accent)' : 'var(--border)'}`,
    background: primary ? 'var(--accent-soft)' : 'transparent',
    color: primary ? 'var(--accent)' : 'var(--fg)',
    cursor: 'pointer',
  };
}
