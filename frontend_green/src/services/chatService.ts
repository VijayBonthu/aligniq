import api from './api';
import type { Message } from '../types';

export interface ChatHistoryPayload {
  chat_history_id?: string;
  user_id: string;
  document_id: string;
  message: Message[];
  title?: string;
}

export async function saveChat(payload: ChatHistoryPayload): Promise<{ chat_history_id: string }> {
  const { data } = await api.post('/chat', payload);
  return data;
}
