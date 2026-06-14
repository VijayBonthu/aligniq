import api from './api';

export interface PublicQuestion {
  question_id: string;
  question_number: string;
  area_or_category: string | null;
  question_text: string;
  answer: string;
  prefilled?: boolean;  // firm seeded a starting answer — still editable by the client
}

export interface Respondent { name: string; designation?: string; email: string; }

export interface PublicQuestionnaire {
  firm: { name: string; logo_url: string | null; primary_color: string | null } | null;
  questions: PublicQuestion[];
  count: number;
  submitted_at?: string | null;
  respondent?: Respondent | null;
}

export interface ReadinessFeedback {
  readiness_status: string;
  readiness_score: number;
  assumptions: { question_id: string; assumption: string; risk_level: string }[];
  vague_answers: { question_id: string; note: string }[];
  contradictions: { detail: string }[];
}

/** PUBLIC (no login). Fetch the client questionnaire for a share token. */
export async function getPublicQuestionnaire(token: string): Promise<PublicQuestionnaire> {
  const { data } = await api.get(`/public/questionnaire/${token}`);
  return data as PublicQuestionnaire;
}

/** PUBLIC (no login). Save answers keyed by question_id (no submit signal). */
export async function submitPublicAnswers(token: string, answers: Record<string, string>) {
  const { data } = await api.post(`/public/questionnaire/${token}/answers`, { answers });
  return data;
}

/** PUBLIC (no login). Ephemeral readiness self-check — saves answers, returns guidance. */
export async function checkPublicReadiness(token: string, answers: Record<string, string>): Promise<ReadinessFeedback> {
  const { data } = await api.post(`/public/questionnaire/${token}/check-readiness`, { answers });
  return data as ReadinessFeedback;
}

/** PUBLIC (no login). Final submit → firm reviews. Captures who completed it. */
export async function finalizePublicQuestionnaire(token: string, answers: Record<string, string>, respondent: Respondent) {
  const { data } = await api.post(`/public/questionnaire/${token}/submit`, { answers, respondent });
  return data;
}
