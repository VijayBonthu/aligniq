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

// ── Public contact form (no account needed) ──────────────────────────────────
// The visitor picks a topic; sales/pricing route to the sales inbox, the rest to
// support. Guarded server-side by Turnstile + a honeypot + a per-IP rate limit.
export type ContactTopic = 'general' | 'sales' | 'account' | 'bug';

export interface PublicContactResponse {
  ref_code: string;
  status: string;
}

export async function submitPublicContact(p: {
  name: string;
  email: string;
  topic: ContactTopic;
  message: string;
  turnstileToken?: string;
  honeypot?: string; // hidden field; real users leave it blank
}): Promise<PublicContactResponse> {
  const { data } = await api.post<PublicContactResponse>('/contact', {
    name: p.name,
    email: p.email,
    topic: p.topic,
    message: p.message,
    turnstile_token: p.turnstileToken || undefined,
    company: p.honeypot || undefined,
  });
  return data;
}
