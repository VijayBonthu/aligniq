// Launch promo — shared by EVERY pricing surface (PricingPage, LandingPage's #pricing
// section, UpgradeModal) so the discount can never show on one and not another. Gated
// build-time on VITE_LAUNCH_OFFER, so the whole promo flips on/off with one env var
// (must be forwarded into the build — see .github/workflows/frontend-deploy.yml).
//
// LAUNCH_DISCOUNT_PCT MUST match the Stripe launch coupon's percent_off (backend
// STRIPE_LAUNCH_COUPON_ID), or the displayed price won't match what Stripe charges.

export const LAUNCH_OFFER = !!import.meta.env.VITE_LAUNCH_OFFER;

export const LAUNCH_DISCOUNT_PCT = 70;

/**
 * "$30" -> "$9" at the launch discount. Non-"$N" prices (Free "$0", Pro "Contact us")
 * are returned unchanged, so only the paid monthly plans get a discounted number.
 */
export function discountedPrice(price: string): string {
  const n = parseFloat(price.replace(/[^0-9.]/g, ''));
  if (!isFinite(n) || n <= 0) return price;
  return `$${Math.round(n * (1 - LAUNCH_DISCOUNT_PCT / 100))}`;
}
