import api from './api';

export interface Firm {
  firm_id: string;
  name: string;
  logo_url: string | null;
  primary_color: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface RateCard {
  rate_id: string;
  firm_id: string;
  role: string;
  seniority: string;
  region: string;
  hourly_rate_usd: number;
  version: number;
  active: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface TeamTemplateRole {
  role: string;
  seniority: string;
  count: number;
  allocation_pct?: number;
}

export interface TeamTemplate {
  template_id: string;
  firm_id: string;
  template_name: string;
  engagement_type: string | null;
  roles: TeamTemplateRole[];
  notes: string | null;
  active: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface TechPreference {
  pref_id: string;
  firm_id: string;
  category: string;
  preferred: string[];
  anti_preferred: string[];
  rationale: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface PastProject {
  project_id: string;
  firm_id: string;
  project_name: string;
  client_name: string | null;
  engagement_type: string | null;
  start_date: string | null;
  end_date: string | null;
  summary: string | null;
  original_brief_md: string | null;
  final_report_md: string | null;
  retrospective_md: string | null;
  effort_estimated_weeks: number | null;
  effort_actual_weeks: number | null;
  created_at?: string;
  updated_at?: string;
}

// -----------------------------------------------------------------------------
// Firm
// -----------------------------------------------------------------------------

export async function getMyFirm() {
  const { data } = await api.get<Firm & { firm_role?: string }>('firm/me');
  return data;
}

export async function updateMyFirm(body: Partial<Pick<Firm, 'name' | 'logo_url' | 'primary_color'>>) {
  const { data } = await api.patch<Firm>('firm/me', body);
  return data;
}

// -----------------------------------------------------------------------------
// Rate cards
// -----------------------------------------------------------------------------

export async function listRateCards(activeOnly = true) {
  const { data } = await api.get<RateCard[]>('firm/rate-cards', {
    params: { active_only: activeOnly },
  });
  return data;
}

export async function createRateCard(body: Omit<RateCard, 'rate_id' | 'firm_id' | 'created_at' | 'updated_at'>) {
  const { data } = await api.post<RateCard>('firm/rate-cards', body);
  return data;
}

export async function updateRateCard(rateId: string, body: Partial<RateCard>) {
  const { data } = await api.patch<RateCard>(`firm/rate-cards/${rateId}`, body);
  return data;
}

export async function deleteRateCard(rateId: string) {
  await api.delete(`firm/rate-cards/${rateId}`);
}

// -----------------------------------------------------------------------------
// Team templates
// -----------------------------------------------------------------------------

export async function listTeamTemplates() {
  const { data } = await api.get<TeamTemplate[]>('firm/team-templates');
  return data;
}

export async function createTeamTemplate(body: Omit<TeamTemplate, 'template_id' | 'firm_id' | 'created_at' | 'updated_at'>) {
  const { data } = await api.post<TeamTemplate>('firm/team-templates', body);
  return data;
}

export async function updateTeamTemplate(templateId: string, body: Partial<TeamTemplate>) {
  const { data } = await api.patch<TeamTemplate>(`firm/team-templates/${templateId}`, body);
  return data;
}

export async function deleteTeamTemplate(templateId: string) {
  await api.delete(`firm/team-templates/${templateId}`);
}

// -----------------------------------------------------------------------------
// Tech preferences
// -----------------------------------------------------------------------------

export async function listTechPreferences() {
  const { data } = await api.get<TechPreference[]>('firm/tech-preferences');
  return data;
}

export async function createTechPreference(body: Omit<TechPreference, 'pref_id' | 'firm_id' | 'created_at' | 'updated_at'>) {
  const { data } = await api.post<TechPreference>('firm/tech-preferences', body);
  return data;
}

export async function updateTechPreference(prefId: string, body: Partial<TechPreference>) {
  const { data } = await api.patch<TechPreference>(`firm/tech-preferences/${prefId}`, body);
  return data;
}

export async function deleteTechPreference(prefId: string) {
  await api.delete(`firm/tech-preferences/${prefId}`);
}

// -----------------------------------------------------------------------------
// Past projects
// -----------------------------------------------------------------------------

export async function listPastProjects() {
  const { data } = await api.get<PastProject[]>('firm/past-projects');
  return data;
}

export async function getPastProject(projectId: string) {
  const { data } = await api.get<PastProject>(`firm/past-projects/${projectId}`);
  return data;
}

export async function createPastProject(body: Omit<PastProject, 'project_id' | 'firm_id' | 'created_at' | 'updated_at'>) {
  const { data } = await api.post<PastProject>('firm/past-projects', body);
  return data;
}

export async function updatePastProject(projectId: string, body: Partial<PastProject>) {
  const { data } = await api.patch<PastProject>(`firm/past-projects/${projectId}`, body);
  return data;
}

export async function deletePastProject(projectId: string) {
  await api.delete(`firm/past-projects/${projectId}`);
}

export async function bulkUploadPastProjects(file: File) {
  const form = new FormData();
  form.append('file', file);
  const { data } = await api.post<{ inserted: number; failed: number; errors?: string[] }>(
    'firm/past-projects/bulk',
    form,
    { headers: { 'Content-Type': 'multipart/form-data' } },
  );
  return data;
}
