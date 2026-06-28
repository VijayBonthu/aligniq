import api from './api';

export type SupportCategory = 'bug' | 'idea' | 'question' | 'billing';

export interface SupportTicketResponse {
  ticket_id: string;
  ref_code: string;
  status: string;
}

export async function submitSupportRequest(p: {
  category: SupportCategory;
  subject: string;
  message: string;
  screenshots: File[];
}): Promise<SupportTicketResponse> {
  const form = new FormData();
  form.append('category', p.category);
  form.append('subject', p.subject);
  form.append('message', p.message);
  p.screenshots.forEach(f => form.append('screenshot', f));

  const { data } = await api.post<SupportTicketResponse>('/support/tickets', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return data;
}
