import api from './api';

export async function getQuestions(presalesId: string) {
  const { data } = await api.get(`/presales/${presalesId}/questions`);
  return data;
}

export interface AnswerSubmission {
  question_id: string;
  answer: string;
}

/** Enriched question shape (A1/A2). Older rows may leave the new fields null. */
export type QuestionPriority = 'blocking' | 'clarifying' | 'optional';
export type QuestionRole = 'business' | 'technical' | 'security' | 'procurement';

export interface PresalesQuestion {
  question_id: string;
  question_type: string;
  question_number: string;
  display_order: number;
  area_or_category?: string | null;
  title?: string | null;
  description?: string | null;
  impact_description?: string | null;
  question_text: string;
  priority?: QuestionPriority | null;
  theme?: string | null;
  respondent_role?: QuestionRole | null;
  estimate_impact?: string | null;
  default_assumption?: string | null;
  default_assumption_risk?: 'low' | 'medium' | 'high' | null;
  answer?: string | null;
  answer_quality?: string | null;
  status?: string | null;
}

/**
 * Submit answers keyed by `question_id` (F6). Backend validates every id
 * belongs to this presales_id and 422s on unknown ids. `additionalContext`
 * (when provided) is persisted durably on the analysis so the analyzer and
 * the CRD both see it — previously it only rode on report generation.
 */
export async function saveAnswers(
  presalesId: string,
  answers: AnswerSubmission[],
  additionalContext?: string,
) {
  const form = new FormData();
  form.append('answers', JSON.stringify(answers));
  if (additionalContext !== undefined) form.append('additional_context', additionalContext);
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

/** Create (or fetch) the public client-questionnaire link. Returns { token }. */
export async function createShareLink(presalesId: string): Promise<{ token: string; presales_id: string }> {
  const { data } = await api.post(`/presales/${presalesId}/share-link`);
  return data;
}

export async function revokeShareLink(presalesId: string) {
  const { data } = await api.delete(`/presales/${presalesId}/share-link`);
  return data;
}

/** Ensure a link, store the client's email, and email them the questionnaire. */
export async function sendClientLink(presalesId: string, clientEmail: string, message?: string): Promise<{ token: string; link: string; emailed: boolean }> {
  const { data } = await api.post(`/presales/${presalesId}/send-client-link`, { client_email: clientEmail, message });
  return data;
}

/** Re-send the questionnaire email to the stored client email. */
export async function sendReminder(presalesId: string): Promise<{ emailed: boolean; link: string }> {
  const { data } = await api.post(`/presales/${presalesId}/send-reminder`);
  return data;
}

/** Mark the link as shared manually (when email isn't used) so the dashboard shows "sent". */
export async function markLinkShared(presalesId: string): Promise<{ token: string; link: string; shared: boolean }> {
  const { data } = await api.post(`/presales/${presalesId}/mark-link-shared`);
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
