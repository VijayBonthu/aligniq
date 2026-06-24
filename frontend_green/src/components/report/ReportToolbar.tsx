import { useState } from 'react';
import { toast } from 'react-hot-toast';
import { exportMarkdownToPdf } from '../../utils/exportPdf';
import { exportMarkdownToDocx } from '../../utils/exportDocx';

interface Props {
  /** Live DOM node to snapshot for PDF (the rendered report container). */
  getReportNode: () => HTMLElement | null;
  /** Original markdown source (used by the DOCX walker). */
  markdown: string;
  /** Used as both the docx title and the download filename stem. */
  title: string;
  /** Optional extra trailing buttons (e.g. "Open in Chat" on ReportStep). */
  trailing?: React.ReactNode;
}

function safeFilename(stem: string): string {
  return (stem || 'report').replace(/[\\/:*?"<>|]+/g, '_').slice(0, 80);
}

/**
 * Mermaid diagrams render asynchronously into the live DOM. Both exporters
 * read that DOM (PDF clones it, DOCX rasterizes the rendered SVGs), so wait
 * until no diagram is still in its loading state before snapshotting —
 * otherwise diagrams come out missing or, for DOCX, shifted out of position.
 * Bounded so a permanently-stuck diagram can't block the download forever.
 */
async function waitForDiagrams(node: HTMLElement, timeoutMs = 6000): Promise<void> {
  const start = Date.now();
  while (node.querySelectorAll('.diagram-block--loading').length > 0) {
    if (Date.now() - start > timeoutMs) break;
    await new Promise((r) => setTimeout(r, 100));
  }
}

export default function ReportToolbar({ getReportNode, markdown, title, trailing }: Props) {
  const [busy, setBusy] = useState<'pdf' | 'docx' | null>(null);

  const handlePdf = async () => {
    const node = getReportNode();
    setBusy('pdf');
    try {
      if (node) await waitForDiagrams(node);
      await exportMarkdownToPdf(markdown, `${safeFilename(title)}.pdf`, { title, node });
    } catch (err) {
      console.error(err);
      toast.error('PDF export failed.');
    } finally {
      setBusy(null);
    }
  };

  const handleDocx = async () => {
    const node = getReportNode();
    setBusy('docx');
    try {
      if (node) await waitForDiagrams(node);
      await exportMarkdownToDocx(markdown, `${safeFilename(title)}.docx`, { title, node });
    } catch (err) {
      console.error(err);
      toast.error('DOCX export failed.');
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="report-toolbar">
      <button type="button" className="report-toolbar__btn" onClick={handlePdf} disabled={!!busy}>
        {busy === 'pdf' ? 'Building PDF…' : 'Download PDF'}
      </button>
      <button type="button" className="report-toolbar__btn" onClick={handleDocx} disabled={!!busy}>
        {busy === 'docx' ? 'Building DOCX…' : 'Download DOCX'}
      </button>
      {trailing}
    </div>
  );
}
