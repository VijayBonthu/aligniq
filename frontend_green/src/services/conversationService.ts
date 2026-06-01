import api from './api';
import { GroupedConversations, ConversationMetadata, Message } from '../types';

export const fetchConversations = async (): Promise<GroupedConversations> => {
  const response = await api.get(`/chat?_t=${Date.now()}`);
  const grouped: GroupedConversations = { today: [], yesterday: [], lastWeek: [], older: [] };

  if (response.data?.user_details && Array.isArray(response.data.user_details)) {
    const sorted = [...response.data.user_details].sort(
      (a: ConversationMetadata, b: ConversationMetadata) =>
        new Date(b.modified_at).getTime() - new Date(a.modified_at).getTime()
    );

    const now = new Date();
    const yesterday = new Date(now);
    yesterday.setDate(yesterday.getDate() - 1);
    const lastWeek = new Date(now);
    lastWeek.setDate(lastWeek.getDate() - 7);

    sorted.forEach((conv: ConversationMetadata) => {
      const d = new Date(conv.modified_at);
      if (d.toDateString() === now.toDateString()) grouped.today.push(conv);
      else if (d.toDateString() === yesterday.toDateString()) grouped.yesterday.push(conv);
      else if (d > lastWeek) grouped.lastWeek.push(conv);
      else grouped.older.push(conv);
    });
  }

  return grouped;
};

export const getConversation = async (chatHistoryId: string) => {
  const response = await api.get(`/chat/${chatHistoryId}`);
  const details = response.data?.user_details;
  if (!details) return response.data;

  let messages: Message[] = [];
  try {
    messages = typeof details.message === 'string' ? JSON.parse(details.message) : (details.message || []);
  } catch { messages = []; }

  return {
    id: details.chat_history_id,
    title: details.title,
    created_at: details.modified_at,
    messages,
    document_id: details.document_id || '',
    chat_history_id: details.chat_history_id,
    modified_at: details.modified_at,
    analysis_mode: details.analysis_mode,
    presales_id: details.presales_id,
  };
};

export const deleteConversation = async (chatId: string): Promise<void> => {
  try {
    await api.delete(`/chat/${chatId}`);
  } catch (err: unknown) {
    if (err && typeof err === 'object' && 'response' in err) {
      const axErr = err as { response?: { status?: number } };
      if (axErr.response?.status === 404) return;
    }
    throw err;
  }
};
