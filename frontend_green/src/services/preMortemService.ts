import api from './api';
import type {
  ItemAction,
  ItemActionResult,
  Sources,
  Thread,
  ThreadResponse,
  TurnKind,
} from '../types/preMortem';

export async function getThread(chatHistoryId: string): Promise<ThreadResponse> {
  const { data } = await api.get<ThreadResponse>(`/pre-mortem/${chatHistoryId}`);
  return data;
}

export async function postTurn(
  chatHistoryId: string,
  body: { user_message: string; kind: TurnKind },
): Promise<{ thread: Thread }> {
  const { data } = await api.post<{ thread: Thread }>(
    `/pre-mortem/${chatHistoryId}/turn`,
    body,
  );
  return data;
}

export async function addPanelist(
  chatHistoryId: string,
  body: { label: string; concern?: string },
): Promise<{ thread: Thread; panelist_id: string }> {
  const { data } = await api.post<{ thread: Thread; panelist_id: string }>(
    `/pre-mortem/${chatHistoryId}/panelist`,
    body,
  );
  return data;
}

export async function removePanelist(
  chatHistoryId: string,
  panelistId: string,
): Promise<{ thread: Thread }> {
  const { data } = await api.delete<{ thread: Thread }>(
    `/pre-mortem/${chatHistoryId}/panelist/${panelistId}`,
  );
  return data;
}

export async function applyItemAction(
  chatHistoryId: string,
  body: { turn_id: string; panelist_id: string; item_id: string; action: ItemAction },
): Promise<{ thread: Thread; action_result: ItemActionResult }> {
  const { data } = await api.post<{ thread: Thread; action_result: ItemActionResult }>(
    `/pre-mortem/${chatHistoryId}/item-action`,
    body,
  );
  return data;
}

export async function resetThread(chatHistoryId: string): Promise<{ thread: Thread }> {
  const { data } = await api.delete<{ thread: Thread }>(`/pre-mortem/${chatHistoryId}`);
  return data;
}

export async function getSources(chatHistoryId: string): Promise<Sources> {
  const { data } = await api.get<Sources>(`/pre-mortem/${chatHistoryId}/sources`);
  return data;
}
