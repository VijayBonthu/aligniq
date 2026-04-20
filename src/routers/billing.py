"""
Billing router — Stripe checkout, customer portal, subscription status,
webhook handler, and admin Pro tier override.

IMPORTANT: The /webhooks/stripe endpoint reads raw bytes for signature
verification. Do NOT use a JSON body parser on this route.
"""
from __future__ import annotations

import json
import stripe
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from config import settings
from models import get_db, User
from utils.token_generation import token_validator
from utils.subscription import TIER_LIMITS, get_or_create_usage_period, get_usage_summary

stripe.api_key = settings.STRIPE_SECRET_KEY

router = APIRouter()

# ------------------------------------------------------------------
# Price ID ↔ tier mapping — must stay in sync with Stripe dashboard
# ------------------------------------------------------------------
PRICE_TO_TIER: dict[str, str] = {}
TIER_TO_PRICE: dict[str, str] = {}

def _build_price_maps():
    if settings.STRIPE_BASIC_PRICE_ID:
        PRICE_TO_TIER[settings.STRIPE_BASIC_PRICE_ID] = "basic"
        TIER_TO_PRICE["basic"] = settings.STRIPE_BASIC_PRICE_ID
    if settings.STRIPE_PLUS_PRICE_ID:
        PRICE_TO_TIER[settings.STRIPE_PLUS_PRICE_ID] = "plus"
        TIER_TO_PRICE["plus"] = settings.STRIPE_PLUS_PRICE_ID

_build_price_maps()


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


# ------------------------------------------------------------------
# POST /billing/checkout-session?tier=basic|plus
# ------------------------------------------------------------------
@router.post("/billing/checkout-session")
async def create_checkout_session(
    tier: str,
    current_user: dict = Depends(token_validator),
    db: Session = Depends(get_db),
):
    """Create a Stripe Checkout session. Returns {checkout_url}."""
    if tier not in TIER_TO_PRICE:
        raise HTTPException(status_code=400, detail="Invalid tier. Must be 'basic' or 'plus'.")

    user_id = current_user["regular_login_token"]["id"]
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Prevent duplicate subscriptions — redirect to portal if already subscribed
    if user.stripe_subscription_id and user.subscription_tier == tier:
        raise HTTPException(status_code=400, detail=f"You are already on the {tier} plan.")

    customer_id = _get_or_create_customer(user, db)

    session = stripe.checkout.Session.create(
        customer=customer_id,
        payment_method_types=["card"],
        line_items=[{"price": TIER_TO_PRICE[tier], "quantity": 1}],
        mode="subscription",
        success_url=f"{settings.FRONTEND_URL}/dashboard?upgrade=success",
        cancel_url=f"{settings.FRONTEND_URL}/pricing?upgrade=cancelled",
        metadata={"user_id": user_id, "tier": tier},
    )
    return {"checkout_url": session.url}


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
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid Stripe signature")
    except Exception:
        raise HTTPException(status_code=400, detail="Webhook processing error")

    # Parse raw JSON for data — Stripe SDK v5+ objects don't support .get()
    event_dict = json.loads(payload)
    event_type = event_dict["type"]
    data_obj = event_dict["data"]["object"]

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
    tier = _resolve_tier(sub)
    stripe_status = sub.get("status", "active")
    user.subscription_tier = tier
    user.stripe_subscription_id = sub.get("id")
    user.subscription_period_end = datetime.fromtimestamp(
        sub.get("current_period_end", 0), tz=timezone.utc
    )
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
            user.subscription_period_end = datetime.fromtimestamp(
                sub["current_period_end"], tz=timezone.utc
            )
        except Exception:
            pass
    db.commit()


# ------------------------------------------------------------------
# POST /admin/set-pro-tier?email=...
# Manually promote a user to Pro — requires X-Admin-Key header
# ------------------------------------------------------------------
@router.post("/admin/set-pro-tier")
async def set_pro_tier(
    email: str,
    x_admin_key: str = Header(...),
    db: Session = Depends(get_db),
):
    if not settings.ADMIN_SECRET_KEY or x_admin_key != settings.ADMIN_SECRET_KEY:
        raise HTTPException(status_code=403, detail="Forbidden")
    user = db.query(User).filter(User.email_address == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.subscription_tier = "pro"
    user.subscription_status = "active"
    db.commit()
    return {"message": f"User {email} promoted to Pro tier"}


# ------------------------------------------------------------------
# GET /billing/publishable-key
# Returns the Stripe publishable key to the frontend safely
# ------------------------------------------------------------------
@router.get("/billing/publishable-key")
async def get_publishable_key():
    return {"publishable_key": settings.STRIPE_PUBLISHABLE_KEY}
