import ReportContent from '../report/ReportContent';

interface Props {
  content: string;
}

// Chat replies render through the same robust pipeline as reports (mermaid +
// ascii diagrams, new-tab citation links, scrollable tables). `variant="chat"`
// keeps the existing `.chat-markdown` styling.
export default function MarkdownContent({ content }: Props) {
  return <ReportContent content={content} variant="chat" />;
}
