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

export interface CheckoutResponse {
  // new customer -> Stripe Checkout
  checkout_url?: string | null;
  // existing subscriber upgrade applied in place (prorated, same cycle) — no redirect
  updated?: boolean;
  tier?: string;
  // downgrade -> Stripe Customer Portal
  requires_portal?: boolean;
  portal_url?: string;
}

export async function createCheckoutSession(tier: 'basic' | 'plus'): Promise<CheckoutResponse> {
  const res = await api.post<CheckoutResponse>(`/billing/checkout-session?tier=${tier}`);
  return res.data;
}

/**
 * Start a plan change and handle all three backend outcomes:
 *  - new customer        → redirect to Stripe Checkout (checkout_url)
 *  - downgrade           → redirect to the Stripe Customer Portal (portal_url)
 *  - in-place upgrade    → no redirect; the backend swapped the price on the
 *                          existing subscription with proration. Resolves
 *                          { updated: true } so the caller can refresh the UI.
 */
export async function startPlanChange(tier: 'basic' | 'plus'): Promise<{ updated: boolean }> {
  const res = await createCheckoutSession(tier);
  if (res.requires_portal && res.portal_url) {
    window.location.href = res.portal_url;
    return { updated: false };
  }
  if (res.checkout_url) {
    window.location.href = res.checkout_url;
    return { updated: false };
  }
  return { updated: Boolean(res.updated) };
}

export async function getPortalUrl(): Promise<{ portal_url: string }> {
  const res = await api.get<{ portal_url: string }>('/billing/portal');
  return res.data;
}
