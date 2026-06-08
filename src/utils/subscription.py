"""
Subscription tier enforcement — single source of truth for limits.

All limit checks happen here. Services call these before any billable action.
Never trust the frontend state; always re-check against the database.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text

import models

# ------------------------------------------------------------------
# Tier definitions
# ------------------------------------------------------------------
# Each tier maps to:
#   model_tier          "lite" → cheap model everywhere (free/basic, COGS ~$0.65/report)
#                       "frontier" → SMART_MODEL on plan/decide/judge (plus/pro, ~$1.85)
#                       — the single biggest margin lever.
#   max_chats           active-project cap (None = unlimited/fair-use).
#   messages_per_chat   chat is bundled fair-use, capped per project.
#   report_generations_per_month  ONE pool for the initial full report AND every
#                       regeneration. None = unlimited. free/basic/plus are finite
#                       (whale-guarded); pro is unlimited (contact-sales — margin
#                       is sized per contract, not by a fixed cap).
#   presales_per_month  the cheap presales brief, metered separately.
#   credit_overage      True → exhausting an allowance draws prepaid credits;
#                       False (free) → hard cap, prompt to upgrade.
#   white_label         plus/pro: the firm's logo/colours on exported PDFs.
#   features            entitlement flags gated via has_feature().
# Prices: basic $30, plus $70 (top self-serve + white-label). pro = contact-sales
# (SSO, firm library/templates, unlimited fair-use). free is CAC.
TIER_LIMITS: dict[str, dict] = {
    "free": {
        "model_tier": "lite",
        "max_chats": 1,
        "messages_per_chat": 20,
        "report_generations_per_month": 1,
        "presales_per_month": 3,
        "monthly_report_regen": 1,          # legacy alias kept in sync; do not rely on
        "credit_overage": False,            # free hard-caps → upgrade (the conversion funnel)
        "white_label": False,
        "features": [],
    },
    "basic": {
        "model_tier": "lite",
        "max_chats": 5,
        "messages_per_chat": 60,
        "report_generations_per_month": 10,
        "presales_per_month": 25,
        "monthly_report_regen": 10,
        "credit_overage": True,
        "white_label": False,
        "features": ["docx", "deliverable_builder", "version_compare", "jira"],
    },
    "plus": {                               # $70 — top self-serve tier (white-label)
        "model_tier": "frontier",
        "max_chats": 15,
        "messages_per_chat": 200,
        "report_generations_per_month": 15,
        "presales_per_month": 100,
        "monthly_report_regen": 15,
        "credit_overage": True,
        "white_label": True,                # branding moved down to plus
        "features": ["docx", "deliverable_builder", "version_compare", "jira",
                     "pre_mortem", "section_regen", "priority", "white_label"],
    },
    "pro": {                                # contact-sales — enterprise (SSO, unlimited)
        "model_tier": "frontier",
        "max_chats": None,                  # unlimited active projects (fair-use)
        "messages_per_chat": None,
        "report_generations_per_month": None,  # unlimited (sales-negotiated)
        "presales_per_month": None,
        "monthly_report_regen": None,
        "credit_overage": True,
        "white_label": True,
        "features": ["docx", "deliverable_builder", "version_compare", "jira",
                     "pre_mortem", "section_regen", "priority", "white_label",
                     "firm_library", "templates", "sso"],
    },
}

# ------------------------------------------------------------------
# Credit economics — à-la-carte cost of each billable action, in credits.
# CREDIT_COSTS = round(COGS × CREDIT_MULTIPLIER / CREDIT_VALUE_USD). At the
# defaults (1 credit = $0.10, 4×): frontier report = 74cr ($7.40), lite report =
# 26cr ($2.60), section regen = 8cr ($0.80), presales = 12cr ($1.20). ~75% margin.
# Keep _ACTION_COGS_USD in sync with the cost model in the monetization plan.
# ------------------------------------------------------------------
_ACTION_COGS_USD: dict[str, float] = {
    "report_frontier": 1.85,
    "report_lite":     0.65,
    "section_regen":   0.20,
    "presales":        0.30,
}


def _credits_for(action: str) -> int:
    from config import settings
    cogs = _ACTION_COGS_USD.get(action, 0.0)
    per_credit = settings.CREDIT_VALUE_USD or 0.10
    return max(1, round(cogs * (settings.CREDIT_MULTIPLIER or 4) / per_credit))


def credit_costs() -> dict[str, int]:
    """Live à-la-carte credit prices (recomputed from config so an env tweak to
    the multiplier/value takes effect without code changes)."""
    return {a: _credits_for(a) for a in _ACTION_COGS_USD}


def report_credit_cost(model_tier: str) -> int:
    return _credits_for("report_frontier" if model_tier == "frontier" else "report_lite")


def _get_user(user_id: str, db: Session) -> models.User:
    user = db.query(models.User).filter(models.User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


def get_effective_tier(user: models.User) -> str:
    """The tier whose limits currently apply.

    An unexpired backend comp (comp_tier + comp_expires_at) overrides the real
    subscription_tier. Once the comp lapses we fall back automatically — the check
    is evaluated lazily on every limit check, so no cron/cleanup job is needed.
    """
    comp_tier = getattr(user, "comp_tier", None)
    comp_expires_at = getattr(user, "comp_expires_at", None)
    if comp_tier and comp_expires_at and comp_expires_at > datetime.now(timezone.utc):
        return comp_tier
    return user.subscription_tier or "free"


def _limits_for(user: models.User) -> dict:
    tier = get_effective_tier(user)
    return TIER_LIMITS.get(tier, TIER_LIMITS["free"])


def get_model_tier(user_id: str, db: Session) -> str:
    """'lite' (cheap model — free/basic) or 'frontier' (SMART_MODEL — plus/pro).
    Threaded into the contract pipeline so report COGS tracks the tier's price."""
    return _limits_for(_get_user(user_id, db)).get("model_tier", "lite")


def has_feature(user_id: str, feature: str, db: Session) -> bool:
    """True if the user's effective tier unlocks `feature` (see TIER_LIMITS[...]['features'])."""
    return feature in (_limits_for(_get_user(user_id, db)).get("features") or [])


def pdf_branding_for(user_id: str, db: Session) -> dict:
    """Branding policy for an exported PDF, keyed off the effective tier:
    free → a watermark (export isn't a clean deliverable → upgrade nudge);
    white-label tiers (pro) → the firm's name + primary colour. Returns kwargs
    ready to splat into utils.pdf_generator.generate_pdf_from_markdown."""
    user = _get_user(user_id, db)
    tier = get_effective_tier(user)
    limits = _limits_for(user)
    brand = {"brand_name": "GroundedIQ", "accent_hex": None, "watermark_text": None}
    if tier == "free":
        brand["watermark_text"] = "PREVIEW"
    if limits.get("white_label") and getattr(user, "firm_id", None):
        firm = db.query(models.Firm).filter(models.Firm.firm_id == user.firm_id).first()
        if firm:
            brand["brand_name"] = firm.name or brand["brand_name"]
            brand["accent_hex"] = firm.primary_color
    return brand


def get_user_subscription(user_id: str, db: Session) -> models.User:
    """Return the User row. Raises 404 if not found."""
    return _get_user(user_id, db)


def _current_period_bounds(user: models.User, now: Optional[datetime] = None) -> tuple[datetime, datetime]:
    """
    Period boundaries used by both chat-creation counting and regen tracking.
    Paid users: anchored to subscription_period_end (Stripe billing cycle, ~one month back).
    Free / lapsed users: calendar month.
    Single source for period math so chat and regen limits roll over together.
    """
    now = now or datetime.now(timezone.utc)
    if user.subscription_period_end and user.subscription_period_end > now:
        period_end = user.subscription_period_end
        month = period_end.month - 1 or 12
        year = period_end.year if period_end.month > 1 else period_end.year - 1
        period_start = period_end.replace(year=year, month=month)
        return period_start, period_end
    period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if now.month == 12:
        period_end = now.replace(year=now.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        period_end = now.replace(month=now.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
    return period_start, period_end


def check_chat_limit(user_id: str, db: Session) -> None:
    """
    Raise HTTP 402 if the user has created their plan's allotment of chats this billing period.
    Period-based (not workspace-state) so archive-and-recreate cannot bypass the limit.
    """
    user = _get_user(user_id, db)
    limits = _limits_for(user)
    if limits["max_chats"] is None:
        return
    period_start, _ = _current_period_bounds(user)
    count = (
        db.query(models.ChatHistory)
        .filter(
            models.ChatHistory.user_id == user_id,
            models.ChatHistory.created_at >= period_start,
        )
        .count()
    )
    if count >= limits["max_chats"]:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "Project limit for this billing period reached. Upgrade to create more.",
                "limit_type": "max_chats",
                "current": count,
                "limit": limits["max_chats"],
                "upgrade_url": "/pricing",
            },
        )


def check_message_limit(chat_history_id: str, user_id: str, db: Session) -> None:
    """Raise HTTP 402 if this chat has reached its per-chat message limit."""
    user = _get_user(user_id, db)
    limits = _limits_for(user)
    if limits["messages_per_chat"] is None:
        return
    chat = (
        db.query(models.ChatHistory)
        .filter(models.ChatHistory.chat_history_id == chat_history_id)
        .first()
    )
    if not chat:
        return
    if chat.message_count >= limits["messages_per_chat"]:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "Message limit reached for this chat. Upgrade to send more messages.",
                "limit_type": "messages_per_chat",
                "current": chat.message_count,
                "limit": limits["messages_per_chat"],
                "upgrade_url": "/pricing",
            },
        )


def get_or_create_usage_period(user_id: str, db: Session) -> models.UsageTracking:
    """
    Return the UsageTracking row covering the current point in time.
    Creates a new row if none covers now.
    - Paid users: period anchored to subscription_period_end (Stripe billing cycle).
    - Free users: calendar month.
    """
    now = datetime.now(timezone.utc)
    user = _get_user(user_id, db)

    row = (
        db.query(models.UsageTracking)
        .filter(
            models.UsageTracking.user_id == user_id,
            models.UsageTracking.period_start <= now,
            models.UsageTracking.period_end >= now,
        )
        .first()
    )
    if row:
        return row

    period_start, period_end = _current_period_bounds(user, now)

    row = models.UsageTracking(
        user_id=user_id,
        period_start=period_start,
        period_end=period_end,
        report_regenerations_used=0,
        report_generations_used=0,
        presales_used=0,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def check_regen_limit(user_id: str, db: Session) -> None:
    """Raise HTTP 402 if the user has used all monthly report regenerations."""
    user = _get_user(user_id, db)
    limits = _limits_for(user)
    if limits["monthly_report_regen"] is None:
        return
    usage = get_or_create_usage_period(user_id, db)
    if usage.report_regenerations_used >= limits["monthly_report_regen"]:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "Monthly report regeneration limit reached. Upgrade or wait for the next billing period.",
                "limit_type": "monthly_report_regen",
                "current": usage.report_regenerations_used,
                "limit": limits["monthly_report_regen"],
                "upgrade_url": "/pricing",
            },
        )


# ------------------------------------------------------------------
# Prepaid credit wallet — the universal top-up across all tiers.
# ------------------------------------------------------------------
def get_credit_balance(user_id: str, db: Session) -> int:
    wallet = (
        db.query(models.CreditWallet)
        .filter(models.CreditWallet.user_id == user_id)
        .first()
    )
    return int(wallet.balance_credits) if wallet else 0


def grant_credits(user_id: str, credits: int, reason: str, db: Session,
                  ref_id: Optional[str] = None) -> int:
    """Add credits to the wallet (creating it if needed) and append a ledger row.
    Returns the new balance. Idempotency for Stripe is the caller's job
    (ProcessedStripeEvent), so a redelivered pack purchase isn't double-granted."""
    if credits <= 0:
        return get_credit_balance(user_id, db)
    # Atomic upsert: INSERT or add to the existing balance in one statement.
    row = db.execute(
        text(
            """
            INSERT INTO credit_wallet (user_id, balance_credits, updated_at)
            VALUES (:uid, :c, now())
            ON CONFLICT (user_id)
            DO UPDATE SET balance_credits = credit_wallet.balance_credits + :c,
                          updated_at = now()
            RETURNING balance_credits
            """
        ),
        {"uid": user_id, "c": credits},
    ).fetchone()
    new_balance = int(row[0]) if row else credits
    db.add(models.CreditLedger(
        user_id=user_id, delta=credits, balance_after=new_balance,
        reason=reason, ref_id=ref_id,
    ))
    db.commit()
    return new_balance


def debit_credits(user_id: str, credits: int, action: str, db: Session,
                  ref_id: Optional[str] = None) -> bool:
    """Atomically spend `credits` iff the balance covers them. Returns True on
    success (ledger row written), False if the balance is insufficient — the
    conditional UPDATE makes concurrent debits race-safe (no overspend)."""
    if credits <= 0:
        return True
    row = db.execute(
        text(
            """
            UPDATE credit_wallet
               SET balance_credits = balance_credits - :c, updated_at = now()
             WHERE user_id = :uid AND balance_credits >= :c
            RETURNING balance_credits
            """
        ),
        {"uid": user_id, "c": credits},
    ).fetchone()
    if not row:
        db.rollback()
        return False
    db.add(models.CreditLedger(
        user_id=user_id, delta=-credits, balance_after=int(row[0]),
        reason=action.split(":")[0], action=action, ref_id=ref_id,
    ))
    db.commit()
    return True


# ------------------------------------------------------------------
# Report-generation metering — ONE pool for initial + regenerations.
# This is what closes the loss hole (the initial generation was uncounted).
# ------------------------------------------------------------------
def _report_limit_detail(user: models.User, used: int) -> dict:
    limits = _limits_for(user)
    cost = report_credit_cost(limits.get("model_tier", "lite"))
    return {
        "error": "Monthly report allowance reached. Recharge credits or upgrade your plan."
                 if limits.get("credit_overage")
                 else "Monthly report allowance reached. Upgrade to generate more.",
        "limit_type": "report_generations_per_month",
        "current": used,
        "limit": limits.get("report_generations_per_month"),
        "credit_overage": bool(limits.get("credit_overage")),
        "credit_cost": cost,
        "credit_balance": None,  # filled by callers that have db
        "upgrade_url": "/pricing",
    }


def check_report_generation_limit(user_id: str, db: Session) -> None:
    """Raise HTTP 402 only if the user can neither draw from their monthly report
    allowance NOR pay with credits (when credit_overage is on). Non-consuming peek;
    consume_report_generation() does the actual decrement at enqueue time."""
    user = _get_user(user_id, db)
    limits = _limits_for(user)
    limit = limits.get("report_generations_per_month")
    if limit is None:
        return
    usage = get_or_create_usage_period(user_id, db)
    if usage.report_generations_used < limit:
        return
    if limits.get("credit_overage"):
        cost = report_credit_cost(limits.get("model_tier", "lite"))
        if get_credit_balance(user_id, db) >= cost:
            return
    detail = _report_limit_detail(user, usage.report_generations_used)
    detail["credit_balance"] = get_credit_balance(user_id, db)
    raise HTTPException(status_code=402, detail=detail)


def consume_report_generation(user_id: str, db: Session, ref_id: Optional[str] = None) -> str:
    """Charge one full-report generation. Tries the monthly allowance first
    (atomic check-and-increment), then prepaid credits. Returns the funding
    source ('allowance' | 'credits' | 'unlimited'); raises 402 if neither covers
    it. Call this right BEFORE scheduling the run (not after), passing the run_id
    as ref_id so a failed run can be refunded via refund_report_generation()."""
    user = _get_user(user_id, db)
    limits = _limits_for(user)
    limit = limits.get("report_generations_per_month")
    if limit is None:
        return "unlimited"
    usage = get_or_create_usage_period(user_id, db)
    row = db.execute(
        text(
            """
            UPDATE usage_tracking
               SET report_generations_used = report_generations_used + 1,
                   updated_at = now()
             WHERE id = :id AND report_generations_used < :lim
            RETURNING report_generations_used
            """
        ),
        {"id": usage.id, "lim": limit},
    ).fetchone()
    db.commit()
    if row:
        return "allowance"
    if limits.get("credit_overage"):
        cost = report_credit_cost(limits.get("model_tier", "lite"))
        if debit_credits(user_id, cost, "report", db, ref_id=ref_id):
            return "credits"
    detail = _report_limit_detail(user, usage.report_generations_used)
    detail["credit_balance"] = get_credit_balance(user_id, db)
    raise HTTPException(status_code=402, detail=detail)


def refund_report_generation(user_id: str, run_id: Optional[str], db: Session) -> None:
    """Give back the report unit consumed for a run that FAILED — so a user is
    never charged for a report they didn't get. Idempotent on run_id. Pipelines
    run in minutes, so the consume and this refund are virtually always in the
    same billing period.

    - credit-funded run → refund the credits (real money; the important case);
    - allowance-funded run → decrement the period counter (floored at 0);
    - unlimited (pro) → no-op (nothing was consumed)."""
    if not run_id:
        return
    # Refund the most recent report charge for this run, unless it's already been
    # refunded. Keyed on ledger row ids (not "any refund exists") so a re-charge
    # — e.g. a resume that consumed again under the same run_id — is refundable too.
    debit = (
        db.query(models.CreditLedger)
        .filter(
            models.CreditLedger.ref_id == run_id,
            models.CreditLedger.action == "report",
            models.CreditLedger.delta < 0,
        )
        .order_by(models.CreditLedger.id.desc())
        .first()
    )
    if debit:
        latest_refund = (
            db.query(models.CreditLedger)
            .filter(models.CreditLedger.ref_id == run_id, models.CreditLedger.reason == "refund")
            .order_by(models.CreditLedger.id.desc())
            .first()
        )
        if latest_refund and latest_refund.id > debit.id:
            return  # this charge was already refunded
        grant_credits(user_id, -int(debit.delta), "refund", db, ref_id=run_id)
        return
    # Allowance-funded (no credit debit tagged with this run): give the unit back.
    db.execute(
        text(
            """
            UPDATE usage_tracking
               SET report_generations_used = GREATEST(report_generations_used - 1, 0),
                   updated_at = now()
             WHERE user_id = :uid AND period_start <= now() AND period_end >= now()
            """
        ),
        {"uid": user_id},
    )
    db.commit()


# ------------------------------------------------------------------
# Presales-brief metering — cheap, metered separately from full reports.
# ------------------------------------------------------------------
def check_presales_limit(user_id: str, db: Session) -> None:
    user = _get_user(user_id, db)
    limits = _limits_for(user)
    limit = limits.get("presales_per_month")
    if limit is None:
        return
    usage = get_or_create_usage_period(user_id, db)
    if usage.presales_used < limit:
        return
    if limits.get("credit_overage") and get_credit_balance(user_id, db) >= _credits_for("presales"):
        return
    raise HTTPException(
        status_code=402,
        detail={
            "error": "Monthly presales allowance reached. Recharge credits or upgrade."
                     if limits.get("credit_overage")
                     else "Monthly presales allowance reached. Upgrade to run more.",
            "limit_type": "presales_per_month",
            "current": usage.presales_used,
            "limit": limit,
            "credit_overage": bool(limits.get("credit_overage")),
            "credit_cost": _credits_for("presales"),
            "credit_balance": get_credit_balance(user_id, db),
            "upgrade_url": "/pricing",
        },
    )


def consume_presales(user_id: str, db: Session) -> str:
    user = _get_user(user_id, db)
    limits = _limits_for(user)
    limit = limits.get("presales_per_month")
    if limit is None:
        return "unlimited"
    usage = get_or_create_usage_period(user_id, db)
    row = db.execute(
        text(
            """
            UPDATE usage_tracking
               SET presales_used = presales_used + 1, updated_at = now()
             WHERE id = :id AND presales_used < :lim
            RETURNING presales_used
            """
        ),
        {"id": usage.id, "lim": limit},
    ).fetchone()
    db.commit()
    if row:
        return "allowance"
    if limits.get("credit_overage") and debit_credits(user_id, _credits_for("presales"), "presales", db):
        return "credits"
    # No allowance and no credits — let the caller's check_presales_limit (run
    # earlier) have already 402'd; reaching here means a race, so 402 to be safe.
    raise HTTPException(status_code=402, detail={"error": "Presales allowance exhausted.", "upgrade_url": "/pricing"})


def increment_message_count(chat_history_id: str, user_id: str, db: Session) -> int:
    """
    Atomically increment the message_count for a chat.
    Uses SQL UPDATE ... RETURNING to prevent race conditions from concurrent requests.
    Returns the new count.
    """
    result = db.execute(
        text(
            """
            UPDATE chat_history
               SET message_count = message_count + 1
             WHERE chat_history_id = :cid
               AND user_id = :uid
             RETURNING message_count
            """
        ),
        {"cid": chat_history_id, "uid": user_id},
    )
    db.commit()
    row = result.fetchone()
    return row[0] if row else 0


def increment_regen_count(user_id: str, db: Session) -> int:
    """
    Atomically increment report_regenerations_used for the current period.
    Returns the new count.
    """
    usage = get_or_create_usage_period(user_id, db)
    result = db.execute(
        text(
            """
            UPDATE usage_tracking
               SET report_regenerations_used = report_regenerations_used + 1,
                   updated_at = now()
             WHERE id = :id
             RETURNING report_regenerations_used
            """
        ),
        {"id": usage.id},
    )
    db.commit()
    row = result.fetchone()
    return row[0] if row else 0


def get_usage_summary(user_id: str, db: Session) -> dict:
    """Return full subscription + usage info for the billing endpoint."""
    from models import ChatHistory
    user = _get_user(user_id, db)
    period_start, _ = _current_period_bounds(user)
    chat_count = (
        db.query(ChatHistory)
        .filter(
            ChatHistory.user_id == user_id,
            ChatHistory.created_at >= period_start,
        )
        .count()
    )
    usage = get_or_create_usage_period(user_id, db)
    limits = _limits_for(user)
    effective_tier = get_effective_tier(user)
    base_tier = user.subscription_tier or "free"
    comp_active = effective_tier != base_tier
    return {
        "tier": effective_tier,            # the tier whose limits apply right now
        "base_tier": base_tier,            # the real paid/free tier underneath any comp
        "status": user.subscription_status or "active",
        "period_end": user.subscription_period_end.isoformat() if user.subscription_period_end else None,
        "comp": {
            "active": comp_active,
            "tier": user.comp_tier if comp_active else None,
            "expires_at": user.comp_expires_at.isoformat() if (comp_active and user.comp_expires_at) else None,
        },
        "usage": {
            "chats": chat_count,
            "report_regenerations_used": usage.report_regenerations_used,
            "report_generations_used": usage.report_generations_used,
            "presales_used": usage.presales_used,
        },
        "limits": limits,
        "credits": {
            "balance": get_credit_balance(user_id, db),
            "costs": credit_costs(),       # à-la-carte price of each action, in credits
            "overage_enabled": bool(limits.get("credit_overage")),
        },
    }
