import { useState } from 'react';
import { toast } from 'react-hot-toast';
import { exportNodeToPdf } from '../../utils/exportPdf';
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

export default function ReportToolbar({ getReportNode, markdown, title, trailing }: Props) {
  const [busy, setBusy] = useState<'pdf' | 'docx' | null>(null);

  const handlePdf = async () => {
    const node = getReportNode();
    if (!node) {
      toast.error('Nothing to export.');
      return;
    }
    setBusy('pdf');
    try {
      await exportNodeToPdf(node, `${safeFilename(title)}.pdf`, { title });
    } catch (err) {
      console.error(err);
      toast.error('PDF export failed.');
    } finally {
      setBusy(null);
    }
  };

  const handleDocx = async () => {
    setBusy('docx');
    try {
      await exportMarkdownToDocx(markdown, `${safeFilename(title)}.docx`, { title });
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
