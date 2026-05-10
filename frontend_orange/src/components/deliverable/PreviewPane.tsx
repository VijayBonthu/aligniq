import { forwardRef, useMemo } from 'react';
import ReportContent from '../report/ReportContent';
import type {
  CustomSection,
  DeliverableSection,
  PolishedSection,
} from '../../types/deliverable';

interface Props {
  sections: DeliverableSection[];
  excludedIds: Set<string>;
  sectionEdits: Record<string, string>;
  polished: Record<string, PolishedSection>;
  customSections: CustomSection[];
}

function assemble({
  sections,
  excludedIds,
  sectionEdits,
  polished,
  customSections,
}: Props): string {
  const childrenByH2 = new Map<string, string[]>();
  for (const s of sections) {
    if (s.heading_level === 3 && s.parent_id) {
      const list = childrenByH2.get(s.parent_id) ?? [];
      list.push(s.id);
      childrenByH2.set(s.parent_id, list);
    }
  }
  const h2ToDrop = new Set<string>();
  for (const [h2, children] of childrenByH2.entries()) {
    if (children.every((cid) => excludedIds.has(cid))) h2ToDrop.add(h2);
  }

  const customsByAnchor = new Map<string, CustomSection[]>();
  for (const cs of customSections) {
    const anchor = cs.position?.after_section_id ?? '__end__';
    const list = customsByAnchor.get(anchor) ?? [];
    list.push(cs);
    customsByAnchor.set(anchor, list);
  }

  const parts: string[] = [];
  for (const s of sections) {
    if (excludedIds.has(s.id)) continue;
    if (s.heading_level === 2 && h2ToDrop.has(s.id)) {
      const customs = customsByAnchor.get(s.id);
      if (customs) {
        for (const cs of customs) {
          const md = (cs.markdown ?? '').trimEnd();
          if (md.trim()) parts.push(md + '\n');
        }
        customsByAnchor.delete(s.id);
      }
      continue;
    }
    const polishedMd = polished[s.id]?.markdown;
    const editMd = sectionEdits[s.id];
    if (polishedMd) parts.push(polishedMd.trimEnd() + '\n');
    else if (editMd) parts.push(editMd.trimEnd() + '\n');
    else parts.push(s.raw_markdown);

    const customs = customsByAnchor.get(s.id);
    if (customs) {
      for (const cs of customs) {
        const md = (cs.markdown ?? '').trimEnd();
        if (md.trim()) parts.push(md + '\n');
      }
      customsByAnchor.delete(s.id);
    }
  }

  for (const customs of customsByAnchor.values()) {
    for (const cs of customs) {
      const md = (cs.markdown ?? '').trimEnd();
      if (md.trim()) parts.push(md + '\n');
    }
  }

  return parts.join('\n').trimEnd() + '\n';
}

export function buildAssembledMarkdown(props: Props): string {
  return assemble(props);
}

const PreviewPane = forwardRef<HTMLDivElement, Props>(function PreviewPane(props, ref) {
  const markdown = useMemo(() => assemble(props), [
    props.sections,
    props.excludedIds,
    props.sectionEdits,
    props.polished,
    props.customSections,
  ]);
  return (
    <div ref={ref} style={{ padding: '24px 28px' }}>
      <ReportContent content={markdown} variant="report" />
    </div>
  );
});

export default PreviewPane;
