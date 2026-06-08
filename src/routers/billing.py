"""
Billing router — Stripe checkout, in-place plan changes, customer portal,
subscription status, webhook handler, and admin comp grants.

IMPORTANT: The /webhooks/stripe endpoint reads raw bytes for signature
verification. Do NOT use a JSON body parser on this route.
"""
from __future__ import annotations

import json
import logging
import stripe
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
from typing import Optional

from config import settings
from models import get_db, User, ProcessedStripeEvent, CreditLedger
from utils.token_generation import token_validator
from utils.subscription import TIER_LIMITS, get_or_create_usage_period, get_usage_summary, grant_credits

stripe.api_key = settings.STRIPE_SECRET_KEY
# Pin the API version so request/response shapes are stable across stripe-python
# upgrades (notably the location of current_period_end). Webhook payloads still
# arrive in the account/endpoint version, so handlers read that field defensively.
if settings.STRIPE_API_VERSION:
    stripe.api_version = settings.STRIPE_API_VERSION

logger = logging.getLogger(__name__)

router = APIRouter()

# ------------------------------------------------------------------
# Price ID ↔ tier mapping — must stay in sync with Stripe dashboard
# ------------------------------------------------------------------
PRICE_TO_TIER: dict[str, str] = {}
TIER_TO_PRICE: dict[str, str] = {}

# Ordering used to tell an upgrade from a downgrade. Upgrades are applied in place
# with proration; downgrades go through the Customer Portal (Stripe schedules them
# at period end / handles credits) rather than charging/crediting unexpectedly here.
TIER_RANK: dict[str, int] = {"free": 0, "basic": 1, "plus": 2, "pro": 3}

# Comps may grant these tiers (granting "free" is meaningless).
COMP_TIERS = {"basic", "plus", "pro"}

# Subscription is considered live (eligible for an in-place swap) in these states.
_ACTIVE_SUB_STATES = {"active", "trialing", "past_due"}


def _build_price_maps():
    if settings.STRIPE_BASIC_PRICE_ID:
        PRICE_TO_TIER[settings.STRIPE_BASIC_PRICE_ID] = "basic"
        TIER_TO_PRICE["basic"] = settings.STRIPE_BASIC_PRICE_ID
    if settings.STRIPE_PLUS_PRICE_ID:
        PRICE_TO_TIER[settings.STRIPE_PLUS_PRICE_ID] = "plus"
        TIER_TO_PRICE["plus"] = settings.STRIPE_PLUS_PRICE_ID
    # pro is self-serve when its price id is configured; otherwise contact-sales.
    if settings.STRIPE_PRO_PRICE_ID:
        PRICE_TO_TIER[settings.STRIPE_PRO_PRICE_ID] = "pro"
        TIER_TO_PRICE["pro"] = settings.STRIPE_PRO_PRICE_ID

_build_price_maps()


# ------------------------------------------------------------------
# Credit packs — one-time top-ups (Stripe mode=payment). price_id → credit grant.
# ------------------------------------------------------------------
CREDIT_PACK_PRICE_TO_CREDITS: dict[str, int] = {}
CREDIT_PACK_SIZE_TO_PRICE: dict[str, str] = {}


def _build_credit_pack_maps():
    for size, price_id in (
        ("10",  settings.STRIPE_CREDIT_PACK_10_PRICE_ID),
        ("25",  settings.STRIPE_CREDIT_PACK_25_PRICE_ID),
        ("50",  settings.STRIPE_CREDIT_PACK_50_PRICE_ID),
        ("100", settings.STRIPE_CREDIT_PACK_100_PRICE_ID),
    ):
        if price_id:
            CREDIT_PACK_PRICE_TO_CREDITS[price_id] = int(settings.CREDIT_PACK_GRANTS.get(size, 0))
            CREDIT_PACK_SIZE_TO_PRICE[size] = price_id

_build_credit_pack_maps()


# ------------------------------------------------------------------
# Helper: get or create Stripe Customer for a user
# ------------------------------------------------------------------
def _get_or_create_customer(user: User, db: Session) -> str:
    if user.stripe_customer_id:
        return user.stripe_customer_id
    customer = stripe.Customer.create(
        email=user.email_address,
        name=user.full_name,
        metadata={"user_id": user.user_id},
    )
    user.stripe_customer_id = customer.id
    db.commit()
    return customer.id


def _extract_period_end(sub) -> Optional[int]:
    """Read current_period_end defensively.

    On older API versions it lives on the subscription; on 2025-03-31+ it moved to
    the subscription *item*. Returns the unix timestamp or None (never a 0 epoch,
    which would mark a live user as expired).
    """
    ts = sub.get("current_period_end")
    if ts:
        return ts
    for item in sub.get("items", {}).get("data", []):
        ts = item.get("current_period_end")
        if ts:
            return ts
    return None


# ------------------------------------------------------------------
# POST /billing/checkout-session?tier=basic|plus
# ------------------------------------------------------------------
@router.post("/billing/checkout-session")
async def create_checkout_session(
    tier: str,
    current_user: dict = Depends(token_validator),
    db: Session = Depends(get_db),
):
    """Start or change a subscription.

    - New customers (no live subscription): returns {checkout_url} to Stripe Checkout.
    - Existing subscribers upgrading: swaps the price on the SAME subscription with
      proration (charges only the difference, keeps the billing cycle, usage counters
      continue) and returns {updated: true}. This avoids the double-subscription bug
      where a second Checkout would leave the user paying for both plans.
    - Existing subscribers downgrading: returns {requires_portal, portal_url} so Stripe
      handles the downgrade (scheduled at period end / credited) in the portal.
    """
    if tier not in TIER_TO_PRICE:
        raise HTTPException(
            status_code=400,
            detail=f"Tier not purchasable. Configured: {sorted(TIER_TO_PRICE) or 'none'}.",
        )

    user_id = current_user["regular_login_token"]["id"]
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    target_price = TIER_TO_PRICE[tier]

    # Does this user already have a live Stripe subscription? If so, change it in
    # place instead of creating a second one.
    live_sub = None
    if user.stripe_subscription_id:
        try:
            sub = stripe.Subscription.retrieve(user.stripe_subscription_id)
            if sub.get("status") in _ACTIVE_SUB_STATES:
                live_sub = sub
        except Exception:
            logger.warning("Could not retrieve subscription %s for user %s; falling back to checkout",
                           user.stripe_subscription_id, user_id)

    if live_sub is not None:
        item = live_sub["items"]["data"][0]
        current_price = item["price"]["id"]
        current_tier = PRICE_TO_TIER.get(current_price, user.subscription_tier or "free")

        if current_price == target_price:
            raise HTTPException(status_code=400, detail=f"You are already on the {tier} plan.")

        # Downgrade → let the customer portal handle scheduling/credits.
        if TIER_RANK.get(tier, 0) < TIER_RANK.get(current_tier, 0):
            portal = stripe.billing_portal.Session.create(
                customer=user.stripe_customer_id,
                return_url=f"{settings.FRONTEND_URL}/dashboard",
            )
            return {"requires_portal": True, "portal_url": portal.url}

        # Upgrade → swap the price on the existing subscription, charge the prorated
        # difference now. The customer.subscription.updated webhook will confirm the
        # tier; we also set it optimistically so the UI is correct immediately.
        stripe.Subscription.modify(
            user.stripe_subscription_id,
            items=[{"id": item["id"], "price": target_price}],
            proration_behavior="always_invoice",
            payment_behavior="error_if_incomplete",
            metadata={"user_id": user_id, "tier": tier},
        )
        user.subscription_tier = tier
        db.commit()
        logger.info("In-place upgrade user=%s %s→%s", user_id, current_tier, tier)
        return {"updated": True, "tier": tier, "checkout_url": None}

    # No live subscription → fresh Checkout session.
    customer_id = _get_or_create_customer(user, db)
    session = stripe.checkout.Session.create(
        customer=customer_id,
        payment_method_types=["card"],
        line_items=[{"price": target_price, "quantity": 1}],
        mode="subscription",
        success_url=f"{settings.FRONTEND_URL}/dashboard?upgrade=success",
        cancel_url=f"{settings.FRONTEND_URL}/pricing?upgrade=cancelled",
        metadata={"user_id": user_id, "tier": tier},
    )
    return {"updated": False, "checkout_url": session.url}


# ------------------------------------------------------------------
# POST /billing/credit-checkout?pack=10|25|50|100
# One-time credit-pack purchase (prepaid top-up; mode=payment). Every tier can
# recharge. Credits are granted on the checkout.session.completed webhook.
# ------------------------------------------------------------------
@router.post("/billing/credit-checkout")
async def create_credit_checkout(
    pack: str,
    current_user: dict = Depends(token_validator),
    db: Session = Depends(get_db),
):
    price_id = CREDIT_PACK_SIZE_TO_PRICE.get(pack)
    if not price_id:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid pack. Configured packs: {sorted(CREDIT_PACK_SIZE_TO_PRICE) or 'none'}",
        )
    credits = CREDIT_PACK_PRICE_TO_CREDITS.get(price_id, 0)

    user_id = current_user["regular_login_token"]["id"]
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    customer_id = _get_or_create_customer(user, db)
    session = stripe.checkout.Session.create(
        customer=customer_id,
        payment_method_types=["card"],
        line_items=[{"price": price_id, "quantity": 1}],
        mode="payment",
        success_url=f"{settings.FRONTEND_URL}/pricing?credits=success",
        cancel_url=f"{settings.FRONTEND_URL}/pricing?credits=cancelled",
        # `kind` lets the webhook tell a credit-pack checkout from a subscription
        # one; `credits` is the grant amount, frozen at purchase time.
        metadata={"user_id": user_id, "kind": "credit_pack", "credits": str(credits), "pack": pack},
    )
    return {"checkout_url": session.url, "credits": credits}


# ------------------------------------------------------------------
# GET /billing/portal
# ------------------------------------------------------------------
@router.get("/billing/portal")
async def get_portal_url(
    current_user: dict = Depends(token_validator),
    db: Session = Depends(get_db),
):
    """Return a Stripe Customer Portal URL for managing/cancelling subscriptions."""
    user_id = current_user["regular_login_token"]["id"]
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user or not user.stripe_customer_id:
        raise HTTPException(
            status_code=404,
            detail="No billing account found. Please subscribe first.",
        )
    portal = stripe.billing_portal.Session.create(
        customer=user.stripe_customer_id,
        return_url=f"{settings.FRONTEND_URL}/dashboard",
    )
    return {"portal_url": portal.url}


# ------------------------------------------------------------------
# GET /billing/subscription
# ------------------------------------------------------------------
@router.get("/billing/subscription")
async def get_subscription_status(
    current_user: dict = Depends(token_validator),
    db: Session = Depends(get_db),
):
    """Return current plan, status, and usage counters."""
    user_id = current_user["regular_login_token"]["id"]
    return get_usage_summary(user_id, db)


# ------------------------------------------------------------------
# POST /webhooks/stripe
# Stripe events — raw bytes required for signature verification
# ------------------------------------------------------------------
@router.post("/webhooks/stripe")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid Stripe signature")
    except Exception:
        raise HTTPException(status_code=400, detail="Webhook processing error")

    # Parse raw JSON for data — Stripe SDK v5+ objects don't support .get()
    event_dict = json.loads(payload)
    event_id = event_dict.get("id")
    event_type = event_dict["type"]
    data_obj = event_dict["data"]["object"]

    # Idempotency: ignore an event we've already handled (redelivery / duplicate).
    if event_id:
        seen = (
            db.query(ProcessedStripeEvent)
            .filter(ProcessedStripeEvent.event_id == event_id)
            .first()
        )
        if seen:
            return JSONResponse(content={"received": True, "duplicate": True})

    if event_type == "customer.subscription.created":
        _handle_subscription_upsert(data_obj, db)
    elif event_type == "customer.subscription.updated":
        _handle_subscription_upsert(data_obj, db)
    elif event_type == "customer.subscription.deleted":
        _handle_subscription_deleted(data_obj, db)
    elif event_type == "invoice.payment_failed":
        _handle_payment_failed(data_obj, db)
    elif event_type == "invoice.payment_succeeded":
        _handle_payment_succeeded(data_obj, db)
    elif event_type in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
        # `completed` covers synchronous methods (card → payment_status=paid).
        # `async_payment_succeeded` covers delayed methods that settle later; the
        # handler only grants on payment_status=paid and is idempotent on session
        # id, so a paid `completed` + a later `async_payment_succeeded` won't double-grant.
        _handle_checkout_completed(data_obj, db)

    # Record the event id AFTER handling. Handlers set absolute state, so even if we
    # crash before this commit a redelivery re-applies the same state safely.
    if event_id:
        db.add(ProcessedStripeEvent(event_id=event_id, event_type=event_type))
        try:
            db.commit()
        except Exception:
            db.rollback()

    return JSONResponse(content={"received": True})


def _resolve_tier(subscription_obj) -> str:
    """Extract internal tier name from Stripe Subscription items."""
    items = subscription_obj.get("items", {}).get("data", [])
    for item in items:
        price_id = item.get("price", {}).get("id", "")
        if price_id in PRICE_TO_TIER:
            return PRICE_TO_TIER[price_id]
    return "free"


def _handle_subscription_upsert(sub, db: Session):
    customer_id = sub.get("customer")
    user = db.query(User).filter(User.stripe_customer_id == customer_id).first()
    if not user:
        return

    stripe_status = sub.get("status", "active")
    # A late 'updated' for a dead subscription must not resurrect a paid tier.
    if stripe_status in ("canceled", "incomplete_expired", "unpaid"):
        user.subscription_tier = "free"
        user.subscription_status = "active"
        user.stripe_subscription_id = None
        user.subscription_period_end = None
        db.commit()
        return

    user.subscription_tier = _resolve_tier(sub)
    user.stripe_subscription_id = sub.get("id")
    period_end_ts = _extract_period_end(sub)
    if period_end_ts:
        user.subscription_period_end = datetime.fromtimestamp(period_end_ts, tz=timezone.utc)
    user.subscription_status = "active" if stripe_status == "active" else stripe_status
    db.commit()


def _handle_subscription_deleted(sub, db: Session):
    customer_id = sub.get("customer")
    user = db.query(User).filter(User.stripe_customer_id == customer_id).first()
    if not user:
        return
    user.subscription_tier = "free"
    user.subscription_status = "active"
    user.stripe_subscription_id = None
    user.subscription_period_end = None
    db.commit()


def _handle_checkout_completed(session, db: Session):
    """Grant credits when a credit-pack checkout completes. Subscription
    checkouts are handled by customer.subscription.* and ignored here.

    Idempotent on the Stripe session id: grant_credits is additive (not
    absolute), so we guard against a redelivered event double-granting by
    skipping if a ledger row already cites this session id. (The event-id
    dedup runs before this, but real money warrants belt-and-braces.)"""
    metadata = session.get("metadata") or {}
    if metadata.get("kind") != "credit_pack":
        return
    if session.get("payment_status") not in (None, "paid", "no_payment_required"):
        return
    user_id = metadata.get("user_id")
    try:
        credits = int(metadata.get("credits") or 0)
    except (TypeError, ValueError):
        credits = 0
    if not user_id or credits <= 0:
        return
    session_id = session.get("id")
    already = (
        db.query(CreditLedger)
        .filter(CreditLedger.ref_id == session_id, CreditLedger.reason == "pack_purchase")
        .first()
    )
    if already:
        return
    new_balance = grant_credits(user_id, credits, "pack_purchase", db, ref_id=session_id)
    logger.info("credit pack: granted %s credits to user=%s (session=%s, balance=%s)",
                credits, user_id, session_id, new_balance)


def _handle_payment_failed(invoice, db: Session):
    customer_id = invoice.get("customer")
    user = db.query(User).filter(User.stripe_customer_id == customer_id).first()
    if user:
        user.subscription_status = "past_due"
        db.commit()


def _handle_payment_succeeded(invoice, db: Session):
    customer_id = invoice.get("customer")
    user = db.query(User).filter(User.stripe_customer_id == customer_id).first()
    if not user:
        return
    user.subscription_status = "active"
    subscription_id = invoice.get("subscription")
    if subscription_id:
        try:
            sub = stripe.Subscription.retrieve(subscription_id)
            period_end_ts = _extract_period_end(sub)
            if period_end_ts:
                user.subscription_period_end = datetime.fromtimestamp(period_end_ts, tz=timezone.utc)
        except Exception:
            logger.warning("payment_succeeded: could not refresh period_end for sub %s", subscription_id)
    db.commit()


# ------------------------------------------------------------------
# Admin comp grants — backend-only gifts (no Stripe). Requires X-Admin-Key.
# Restrict /admin/* to your IP at the Cloudflare edge as well (defense in depth).
# ------------------------------------------------------------------
def _require_admin(x_admin_key: str):
    if not settings.ADMIN_SECRET_KEY or x_admin_key != settings.ADMIN_SECRET_KEY:
        raise HTTPException(status_code=403, detail="Forbidden")


@router.post("/admin/grant-comp")
async def grant_comp(
    email: str,
    tier: str,
    days: int,
    x_admin_key: str = Header(...),
    db: Session = Depends(get_db),
):
    """Grant `tier` to a user for `days` days as a comp (free months, complaint
    make-good). Auto-reverts to their real subscription_tier when it lapses —
    get_effective_tier() in utils/subscription.py enforces the expiry lazily."""
    _require_admin(x_admin_key)
    if tier not in COMP_TIERS:
        raise HTTPException(status_code=400, detail=f"tier must be one of {sorted(COMP_TIERS)}")
    if days <= 0 or days > 3650:
        raise HTTPException(status_code=400, detail="days must be between 1 and 3650")

    user = db.query(User).filter(User.email_address == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    expires_at = datetime.now(timezone.utc) + timedelta(days=days)
    user.comp_tier = tier
    user.comp_expires_at = expires_at
    db.commit()
    logger.info("ADMIN comp granted email=%s tier=%s days=%s expires=%s", email, tier, days, expires_at.isoformat())
    return {"message": f"Granted {tier} to {email} for {days} days", "expires_at": expires_at.isoformat()}


@router.post("/admin/revoke-comp")
async def revoke_comp(
    email: str,
    x_admin_key: str = Header(...),
    db: Session = Depends(get_db),
):
    """Clear any active comp; the user reverts to their real subscription tier."""
    _require_admin(x_admin_key)
    user = db.query(User).filter(User.email_address == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.comp_tier = None
    user.comp_expires_at = None
    db.commit()
    logger.info("ADMIN comp revoked email=%s", email)
    return {"message": f"Comp revoked for {email}"}


# ------------------------------------------------------------------
# GET /billing/publishable-key
# Returns the Stripe publishable key to the frontend safely
# ------------------------------------------------------------------
@router.get("/billing/publishable-key")
async def get_publishable_key():
    return {"publishable_key": settings.STRIPE_PUBLISHABLE_KEY}
