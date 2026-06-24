import api from './api';
import type {
  ConfigUpdateResponse,
  DeliverableConfig,
  DeliverableSectionsResponse,
  PolishResponse,
} from '../types/deliverable';

export async function getSections(
  chatHistoryId: string,
): Promise<DeliverableSectionsResponse> {
  const { data } = await api.get<DeliverableSectionsResponse>(
    `/deliverable/${chatHistoryId}/sections`,
  );
  return data;
}

export async function updateConfig(
  chatHistoryId: string,
  config: DeliverableConfig,
): Promise<ConfigUpdateResponse> {
  const { data } = await api.put<ConfigUpdateResponse>(
    `/deliverable/${chatHistoryId}/config`,
    config,
  );
  return data;
}

export async function polishSection(
  chatHistoryId: string,
  sectionId: string,
): Promise<PolishResponse> {
  const { data } = await api.post<PolishResponse>(
    `/deliverable/${chatHistoryId}/polish`,
    { section_id: sectionId },
  );
  return data;
}

export async function revertPolish(
  chatHistoryId: string,
  sectionId: string,
): Promise<{ status: string; section_id: string }> {
  const { data } = await api.delete<{ status: string; section_id: string }>(
    `/deliverable/${chatHistoryId}/polish/${sectionId}`,
  );
  return data;
}
