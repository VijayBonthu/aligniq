export interface IntegrationMeta {
  id: string;
  name: string;
  color: string;
  logo: string;
  desc?: string;
  category?: string;
  connected?: boolean;
  project?: string;
  lastSync?: string;
  pushed?: number;
}

export default function IntLogo({ integ }: { integ: IntegrationMeta }) {
  return (
    <div
      style={{
        width: 28,
        height: 28,
        borderRadius: 6,
        background: `${integ.color}22`,
        border: `1px solid ${integ.color}44`,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontSize: 10,
        fontWeight: 700,
        color: integ.color,
        fontFamily: 'var(--font-mono)',
        flexShrink: 0,
      }}
    >
      {integ.logo}
    </div>
  );
}

export const INTEGRATIONS: IntegrationMeta[] = [
  { id: 'jira', name: 'Jira', desc: 'Push risks & requirements as issues', color: '#0052CC', logo: 'J', category: 'Issue Tracker' },
  { id: 'azure', name: 'Azure DevOps', desc: 'Sync work items and pull backlogs', color: '#0078D4', logo: 'Az', category: 'Issue Tracker' },
  { id: 'github', name: 'GitHub', desc: 'Create issues and link repos', color: '#6e40c9', logo: 'GH', category: 'Code' },
  { id: 'linear', name: 'Linear', desc: 'Push to cycles and triage queue', color: '#5E6AD2', logo: 'L', category: 'Issue Tracker' },
  { id: 'notion', name: 'Notion', desc: 'Export full alignment report as a page', color: '#37352F', logo: 'N', category: 'Docs' },
  { id: 'confluence', name: 'Confluence', desc: 'Publish structured report to space', color: '#0052CC', logo: 'C', category: 'Docs' },
  { id: 'slack', name: 'Slack', desc: 'Send risk alerts & report summaries', color: '#4A154B', logo: 'S', category: 'Comms' },
  { id: 'aws', name: 'AWS', desc: 'Validate architecture against Well-Architected', color: '#FF9900', logo: '⬡', category: 'Cloud' },
];
