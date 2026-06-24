import api from './api';

export type AnnouncementKind = 'info' | 'warning' | 'outage' | 'maintenance' | 'success';

export interface Maintenance {
  on: boolean;
  title: string;
  message: string;
  eta: string;
  media_url?: string;  // optional GIF/image shown on the maintenance page
}

export interface ReadOnlyState {
  on: boolean;
  message: string;
}

export interface PublicAnnouncement {
  id: string;
  kind: AnnouncementKind;
  title: string;
  body?: string | null;
  dismissible: boolean;
  // 'users' = targeted; only ever arrives via getMySiteConfig (server-matched on the
  // caller's email), never the public /site-config.
  audience: 'all' | 'authenticated' | 'users';
  link_url?: string | null;
  link_label?: string | null;
}

export interface ChangelogRef {
  id: string;
  version?: string | null;
  title: string;
}

export interface SiteConfig {
  maintenance: Maintenance;
  read_only: ReadOnlyState;
  announcements: PublicAnnouncement[];
  changelog_latest: ChangelogRef | null;
}

export interface ChangelogEntry {
  id: string;
  version?: string | null;
  title: string;
  body?: string | null;
  category?: string | null;
  media_url?: string | null;  // optional GIF/image shown in "What's new"
  published_at?: string | null;
}

// Public, unauthenticated. The SPA polls this for maintenance/announcements.
export async function getSiteConfig(): Promise<SiteConfig> {
  const { data } = await api.get('/site-config');
  return data;
}

export async function getChangelog(): Promise<ChangelogEntry[]> {
  const { data } = await api.get('/changelog');
  return data.entries || [];
}

export interface MySiteConfig {
  announcements: PublicAnnouncement[];
  // Non-null when THIS account should see the maintenance page (global on, or they're in
  // the targeted/"troll" list) — even while global maintenance is off for everyone else.
  maintenance: Maintenance | null;
}

// Authenticated, per-user overlay: targeted announcements + personal maintenance, matched
// to the signed-in user server-side. Kept off the public endpoint so recipient lists never leak.
export async function getMySiteConfig(): Promise<MySiteConfig> {
  const { data } = await api.get('/my-site-config');
  return { announcements: data.announcements || [], maintenance: data.maintenance || null };
}
