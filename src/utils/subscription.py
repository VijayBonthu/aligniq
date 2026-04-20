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
TIER_LIMITS: dict[str, dict] = {
    "free": {
        "max_chats": 3,
        "messages_per_chat": 25,
        "monthly_report_regen": 2,
    },
    "basic": {
        "max_chats": 8,
        "messages_per_chat": 60,
        "monthly_report_regen": 6,
    },
    "plus": {
        "max_chats": 12,
        "messages_per_chat": 80,
        "monthly_report_regen": 10,
    },
    "pro": {
        "max_chats": None,           # None = unlimited
        "messages_per_chat": None,
        "monthly_report_regen": None,
    },
}


def _get_user(user_id: str, db: Session) -> models.User:
    user = db.query(models.User).filter(models.User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


def _limits_for(user: models.User) -> dict:
    tier = user.subscription_tier or "free"
    return TIER_LIMITS.get(tier, TIER_LIMITS["free"])


def get_user_subscription(user_id: str, db: Session) -> models.User:
    """Return the User row. Raises 404 if not found."""
    return _get_user(user_id, db)


def check_chat_limit(user_id: str, db: Session) -> None:
    """Raise HTTP 402 if the user has reached their active chat limit."""
    user = _get_user(user_id, db)
    limits = _limits_for(user)
    if limits["max_chats"] is None:
        return
    count = (
        db.query(models.ChatHistory)
        .filter(
            models.ChatHistory.user_id == user_id,
            models.ChatHistory.active_tag == True,
        )
        .count()
    )
    if count >= limits["max_chats"]:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "Chat limit reached. Upgrade your plan to create more chats.",
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

    # Determine billing period boundaries
    if user.subscription_period_end and user.subscription_period_end > now:
        period_end = user.subscription_period_end
        # One month back from period_end
        month = period_end.month - 1 or 12
        year = period_end.year if period_end.month > 1 else period_end.year - 1
        period_start = period_end.replace(year=year, month=month)
    else:
        # Calendar month for free-tier users
        period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if now.month == 12:
            period_end = now.replace(year=now.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            period_end = now.replace(month=now.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)

    row = models.UsageTracking(
        user_id=user_id,
        period_start=period_start,
        period_end=period_end,
        report_regenerations_used=0,
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
    chat_count = (
        db.query(ChatHistory)
        .filter(ChatHistory.user_id == user_id, ChatHistory.active_tag == True)
        .count()
    )
    usage = get_or_create_usage_period(user_id, db)
    limits = _limits_for(user)
    return {
        "tier": user.subscription_tier or "free",
        "status": user.subscription_status or "active",
        "period_end": user.subscription_period_end.isoformat() if user.subscription_period_end else None,
        "usage": {
            "chats": chat_count,
            "report_regenerations_used": usage.report_regenerations_used,
        },
        "limits": limits,
    }
