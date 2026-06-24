import api from './api';

// ── Site settings (maintenance / read-only / feature flags) ──
export interface OpsState {
  maintenance: {
    on: boolean; title: string; message: string; eta: string; media_url: string;
    allowlist_ips: string[]; allowlist_emails: string[];
    target_emails: string[];  // targeted/"troll" maintenance recipients
  };
  read_only: { on: boolean; message: string };
  feature_flags: { signups_enabled: boolean; logins_enabled: boolean; pipeline_enabled: boolean };
}

export type SiteSettingsPatch = {
  maintenance?: Partial<OpsState['maintenance']>;
  read_only?: Partial<OpsState['read_only']>;
  feature_flags?: Partial<OpsState['feature_flags']>;
};

export async function getSiteSettings(): Promise<OpsState> {
  const { data } = await api.get('/admin/site-settings');
  return data;
}

export async function putSiteSettings(patch: SiteSettingsPatch): Promise<OpsState> {
  const { data } = await api.put('/admin/site-settings', patch);
  return data;
}

// ── Announcements ──
export interface AdminAnnouncement {
  id: string;
  kind: string;
  title: string;
  body?: string | null;
  active: boolean;
  starts_at?: string | null;
  ends_at?: string | null;
  dismissible: boolean;
  audience: string;  // all | authenticated | users
  link_url?: string | null;
  link_label?: string | null;
  target_emails?: string[] | null;  // recipients when audience='users'
  created_at?: string | null;
  created_by?: string | null;
}

export type AnnouncementInput = Partial<Omit<AdminAnnouncement, 'id' | 'created_at' | 'created_by'>> & {
  title: string;
};

export async function listAnnouncements(): Promise<AdminAnnouncement[]> {
  const { data } = await api.get('/admin/announcements');
  return data.announcements || [];
}
export async function createAnnouncement(body: AnnouncementInput): Promise<AdminAnnouncement> {
  const { data } = await api.post('/admin/announcements', body);
  return data;
}
export async function updateAnnouncement(id: string, body: Partial<AnnouncementInput>): Promise<AdminAnnouncement> {
  const { data } = await api.patch(`/admin/announcements/${id}`, body);
  return data;
}
export async function deleteAnnouncement(id: string): Promise<void> {
  await api.delete(`/admin/announcements/${id}`);
}

// ── Changelog ──
export interface AdminChangelogEntry {
  id: string;
  version?: string | null;
  title: string;
  body?: string | null;
  category?: string | null;
  media_url?: string | null;  // optional GIF/image shown in "What's new"
  published: boolean;
  published_at?: string | null;
  created_at?: string | null;
}

export type ChangelogInput = Partial<Omit<AdminChangelogEntry, 'id' | 'created_at' | 'published_at'>> & {
  title: string;
};

export async function listChangelogAdmin(): Promise<AdminChangelogEntry[]> {
  const { data } = await api.get('/admin/changelog');
  return data.entries || [];
}
export async function createChangelog(body: ChangelogInput): Promise<AdminChangelogEntry> {
  const { data } = await api.post('/admin/changelog', body);
  return data;
}
export async function updateChangelog(id: string, body: Partial<ChangelogInput>): Promise<AdminChangelogEntry> {
  const { data } = await api.patch(`/admin/changelog/${id}`, body);
  return data;
}
export async function deleteChangelog(id: string): Promise<void> {
  await api.delete(`/admin/changelog/${id}`);
}

// ── Staff access (admins manage admins) ──
export interface StaffUser {
  user_id: string;
  email: string;
  full_name?: string | null;
}

export async function listStaff(): Promise<StaffUser[]> {
  const { data } = await api.get('/admin/staff');
  return data.staff || [];
}

export async function setStaff(email: string, is_staff: boolean): Promise<void> {
  await api.post('/admin/staff', { email, is_staff });
}

// ── Per-firm client email templates (staff-managed) ──
export interface FirmRef { firm_id: string; name: string; }

export interface EmailTemplateFields {
  subject?: string; heading?: string; intro?: string; button_label?: string; signoff?: string;
}

export interface FirmEmailTemplates {
  firm_id: string;
  templates: Record<string, { defaults: Required<EmailTemplateFields>; override: EmailTemplateFields }>;
}

export async function listFirms(search?: string): Promise<FirmRef[]> {
  const { data } = await api.get('/admin/firms', { params: search ? { search } : {} });
  return data.firms || [];
}

export async function getFirmEmailTemplates(firmId: string): Promise<FirmEmailTemplates> {
  const { data } = await api.get(`/admin/firm-email-templates/${firmId}`);
  return data;
}

export async function saveFirmEmailTemplate(firmId: string, key: string, fields: EmailTemplateFields): Promise<void> {
  await api.put(`/admin/firm-email-templates/${firmId}/${key}`, fields);
}
