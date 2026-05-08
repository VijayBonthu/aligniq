import api from './api';

export async function getQuestions(presalesId: string) {
  const { data } = await api.get(`/presales/${presalesId}/questions`);
  return data;
}

export async function saveAnswers(presalesId: string, answers: Record<string, string>) {
  const form = new FormData();
  form.append('answers', JSON.stringify(answers));
  const { data } = await api.post(
    `/presales/${presalesId}/questions/answers`,
    form,
    { headers: { 'Content-Type': 'multipart/form-data' } },
  );
  return data;
}

export async function analyze(presalesId: string) {
  const { data } = await api.post(`/presales/${presalesId}/analyze`);
  return data;
}

export async function restoreQuestion(presalesId: string, questionId: string) {
  const { data } = await api.post(`/presales/${presalesId}/questions/${questionId}/restore`);
  return data;
}

export async function presalesChat(presalesId: string, payload: unknown) {
  const { data } = await api.post(`/presales/${presalesId}/chat`, payload);
  return data;
}

export async function getFullPresales(presalesId: string) {
  const { data } = await api.get(`/presales/${presalesId}/full`);
  return data;
}

/**
 * Generate the SHORT presales brief that defines requirements for the
 * later 9-agent full pipeline. Synchronous, ~2-3 min. Returns
 * { report, chat_history_id, presales_id, document_id, title, status }.
 */
export async function generatePresalesReport(
  presalesId: string,
  userAnswers?: string,
  assumptions?: string,
  additionalContext?: string,
) {
  const form = new FormData();
  form.append('presales_id', presalesId);
  if (userAnswers) form.append('user_answers', userAnswers);
  if (assumptions) form.append('assumptions', assumptions);
  if (additionalContext) form.append('additional_context', additionalContext);
  const { data } = await api.post('/generate-presales-report/', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return data as {
    report: string;
    chat_history_id: string;
    presales_id: string;
    document_id: string;
    title: string;
    status: string;
  };
}

/**
 * Overwrite the latest presales_brief markdown saved in the given chat_history.
 * Used by the wizard's Report step Edit/Save flow before the user runs the
 * full pipeline.
 */
export async function updateReport(chatHistoryId: string, content: string) {
  const { data } = await api.patch(`/presales-report/${chatHistoryId}`, { content });
  return data as {
    chat_history_id: string;
    status: string;
    edited_at: string;
  };
}
