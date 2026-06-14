import api from './api';
import type { OverviewResponse } from '../types/overview';

export async function fetchOverview(): Promise<OverviewResponse> {
  const response = await api.get<OverviewResponse>('/projects/overview');
  return response.data;
}

/** Set/clear the firm's display name for a project card (LLM title kept as fallback). */
export async function renameProject(chatHistoryId: string, customTitle: string): Promise<{ custom_title: string | null; title: string }> {
  const { data } = await api.patch(`/projects/${chatHistoryId}/name`, { custom_title: customTitle });
  return data;
}
