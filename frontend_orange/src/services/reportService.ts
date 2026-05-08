import api from './api';

export interface ReportVersionMeta {
  version_number: number;
  created_at: string;
  summary: string;
  is_default: boolean;
  change_description: string;
}

export interface ReportVersionFull {
  version_number: number;
  report_content: string;
  summary_report: string;
  created_at: string;
  is_default: boolean;
  change_description: string;
}

export interface PendingChange {
  change_id: string;
  section: string;
  change_type: 'add' | 'modify' | 'remove';
  proposed_content: string;
  status: 'pending' | 'applied' | 'rejected';
}

export interface Conflict {
  change_id_1: string;
  change_id_2: string;
  conflict_type: string;
}

export interface PendingChangesResponse {
  pending_changes: PendingChange[];
  conflicts: Conflict[];
  affected_sections: string[];
}

export async function getVersions(chatHistoryId: string): Promise<{ total_versions: number; versions: ReportVersionMeta[] }> {
  const { data } = await api.get(`/report-versions/${chatHistoryId}`);
  return data;
}

export async function getVersion(chatHistoryId: string, versionNumber: number): Promise<ReportVersionFull> {
  const { data } = await api.get(`/report-versions/${chatHistoryId}/${versionNumber}`);
  return data;
}

export async function rollbackVersion(chatHistoryId: string, versionNumber: number) {
  const { data } = await api.post(`/report-versions/${chatHistoryId}/rollback/${versionNumber}`);
  return data;
}

export async function getPendingChanges(chatHistoryId: string): Promise<PendingChangesResponse> {
  const { data } = await api.get(`/pending-changes/${chatHistoryId}`);
  return data;
}

export async function removePendingChange(chatHistoryId: string, changeId: string) {
  const { data } = await api.delete(`/pending-changes/${chatHistoryId}/${changeId}`);
  return data;
}

export async function clearPendingChanges(chatHistoryId: string) {
  const { data } = await api.delete(`/pending-changes/${chatHistoryId}`);
  return data;
}
