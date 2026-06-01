import api from './api';

export interface TierLimits {
  max_chats: number | null;
  messages_per_chat: number | null;
  monthly_report_regen: number | null;
}

export interface SubscriptionUsage {
  chats: number;
  report_regenerations_used: number;
}

export interface SubscriptionData {
  tier: 'free' | 'basic' | 'plus' | 'pro';
  status: 'active' | 'past_due' | 'canceled';
  period_end: string | null;
  usage: SubscriptionUsage;
  limits: TierLimits;
}

export async function getSubscription(): Promise<SubscriptionData> {
  const res = await api.get<SubscriptionData>('/billing/subscription');
  return res.data;
}

export async function createCheckoutSession(tier: 'basic' | 'plus'): Promise<{ checkout_url: string }> {
  const res = await api.post<{ checkout_url: string }>(`/billing/checkout-session?tier=${tier}`);
  return res.data;
}

export async function getPortalUrl(): Promise<{ portal_url: string }> {
  const res = await api.get<{ portal_url: string }>('/billing/portal');
  return res.data;
}
