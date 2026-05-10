export type SectionKind = 'standard' | 'internal';

export interface DeliverableSection {
  id: string;
  heading_level: 2 | 3;
  heading_number: string;
  heading_text: string;
  parent_id: string | null;
  raw_markdown: string;
  kind: SectionKind;
}

export interface CustomSection {
  id: string;
  position: { after_section_id: string };
  markdown: string;
}

export interface DeliverableConfig {
  included_section_ids: string[];
  excluded_section_ids: string[];
  section_edits: Record<string, string>;
  custom_sections: CustomSection[];
}

export interface PolishedSection {
  markdown: string;
  polished_at: string;
}

export interface DeliverableSectionsResponse {
  sections: DeliverableSection[];
  config: DeliverableConfig | null;
  polished_sections: Record<string, PolishedSection>;
  default_excluded_ids: string[];
  report_version_id: string;
  updated_at: string | null;
}

export interface PolishResponse {
  section_id: string;
  polished_markdown: string;
}

export interface ConfigUpdateResponse {
  status: string;
  report_version_id: string;
  updated_at: string;
}
