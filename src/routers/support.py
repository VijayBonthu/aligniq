"""In-app Help & Support: a single endpoint that records a user's bug report /
feedback / question and routes the response loop through email.

On submit we:
  1. (optionally) store any screenshots in S3 — the durable record,
  2. persist a `support_tickets` row,
  3. email SUPPORT_INBOX with reply_to = the requester (so the team replies straight
     from their inbox) and the screenshots attached, and
  4. email the requester a "we got it (#ref)" confirmation.

Both emails are best-effort (utils.email.send_email never raises); the ticket is
saved regardless. Auth is "any logged-in user" — deliberately NOT
require_verified_email, since a user struggling to verify may need to reach support.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import os
import re
import time
from datetime import datetime, timezone
from email.utils import parseaddr

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from config import settings
from models import get_db, SupportTicket, SupportMessage, User
from utils.auth_deps import get_current_user_payload
from utils.document_save import get_s3_client, ensure_bucket_exists, upload_document_s3
from utils.email import (
    send_email,
    support_request_internal_html,
    support_confirmation_html,
    SUPPORT_CATEGORY_LABELS,
)
from utils.ids import new_id
from utils.logger import logger

router = APIRouter()

VALID_CATEGORIES = set(SUPPORT_CATEGORY_LABELS.keys())  # bug | idea | question | billing
MAX_SUBJECT_LEN = 200
MAX_MESSAGE_LEN = 5000
MAX_SCREENSHOTS = 3
MAX_SCREENSHOT_BYTES = 5 * 1024 * 1024  # 5 MB each
SUPPORT_S3_FOLDER = "support"


def _ref_code(ticket_id: str) -> str:
    """Human-friendly reference shown to the user. The UUIDv7 PK stays the real id."""
    return "GIQ-" + ticket_id.replace("-", "")[-6:].upper()


@router.post("/support/tickets")
async def create_support_ticket(
    category: str = Form(...),
    subject: str = Form(...),
    message: str = Form(...),
    screenshot: list[UploadFile] = File(default=[]),
    user: dict = Depends(get_current_user_payload),
    db: Session = Depends(get_db),
):
    user_id = user["id"]
    user_email = (user.get("email") or "").strip()

    # ---- validate text ----
    category = (category or "").strip().lower()
    subject = (subject or "").strip()
    message = (message or "").strip()
    if category not in VALID_CATEGORIES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid category.")
    if not subject or len(subject) > MAX_SUBJECT_LEN:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Subject is required and must be ≤ {MAX_SUBJECT_LEN} characters.")
    if not message or len(message) > MAX_MESSAGE_LEN:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Message is required and must be ≤ {MAX_MESSAGE_LEN} characters.")

    # ---- validate + read screenshots (keep bytes for both S3 + email attachment) ----
    files = [f for f in (screenshot or []) if f and f.filename]
    if len(files) > MAX_SCREENSHOTS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"At most {MAX_SCREENSHOTS} screenshots.")
    shots: list[tuple[str, str, bytes]] = []  # (filename, content_type, data)
    for f in files:
        if not (f.content_type or "").startswith("image/"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Screenshots must be image files.")
        data = await f.read()
        if len(data) > MAX_SCREENSHOT_BYTES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Each screenshot must be ≤ 5 MB.")
        shots.append((f.filename, f.content_type, data))

    ticket_id = new_id()
    ref_code = _ref_code(ticket_id)

    # ---- store screenshots in S3 (best-effort; never blocks the ticket) ----
    s3_keys: list[str] = []
    if shots:
        try:
            s3 = get_s3_client()
            ensure_bucket_exists(s3, settings.S3_BUCKET_NAME)
            for i, (fname, ctype, data) in enumerate(shots):
                ext = (os.path.splitext(fname)[1].lstrip(".") or "png").lower()
                key = f"{SUPPORT_S3_FOLDER}/{user_id}/{ticket_id}_{i}.{ext}"
                upload_document_s3(s3, io.BytesIO(data), key, ctype, settings.S3_BUCKET_NAME)
                s3_keys.append(key)
        except Exception as e:  # noqa: BLE001 — screenshot storage is non-critical
            logger.error("Support screenshot upload to S3 failed for ticket %s: %s", ref_code, e)
            s3_keys = []

    # ---- persist the ticket ----
    ticket = SupportTicket(
        ticket_id=ticket_id,
        ref_code=ref_code,
        user_id=user_id,
        requester_email=user_email or None,
        category=category,
        subject=subject,
        message=message,
        screenshot_path=",".join(s3_keys) or None,
        status="open",
    )
    try:
        db.add(ticket)
        db.commit()
    except Exception as e:  # noqa: BLE001
        db.rollback()
        logger.error("Failed to persist support ticket %s: %s", ref_code, e)
        raise HTTPException(status_code=500, detail="Could not save your request. Please try again.")

    # ---- resolve a display name for the emails ----
    user_row = db.query(User).filter(User.user_id == user_id).first()
    user_name = (getattr(user_row, "full_name", None) or "").strip() or user_email or "there"

    # ---- notify the team (reply_to = requester) with screenshots attached ----
    attachments = [
        {"filename": fname, "content": base64.b64encode(data).decode("ascii")}
        for (fname, _ctype, data) in shots
    ]
    cat_label = SUPPORT_CATEGORY_LABELS.get(category, category)
    await send_email(
        to=settings.SUPPORT_INBOX,
        subject=f"[Support] {cat_label}: {subject}"[:200],
        html=support_request_internal_html(
            ref_code=ref_code, category=category, subject=subject, message=message,
            user_name=user_name, user_email=user_email,
        ),
        reply_to=user_email or None,
        attachments=attachments or None,
    )

    # ---- confirm to the user ----
    if user_email:
        await send_email(
            to=user_email,
            subject=f"We got your request ({ref_code})",
            html=support_confirmation_html(user_name, ref_code, subject),
        )

    return {"ticket_id": ticket_id, "ref_code": ref_code, "status": "open"}


# ---------------------------------------------------------------------------
# Inbound email webhook (Resend) — when a user replies to a support email, Resend
# parses it and POSTs an `email.received` event here. The payload is metadata only
# (email_id, from, to, subject, attachment names); the body is fetched best-effort
# via the Receiving API. Signature is verified with the Svix scheme. Mirrors the
# Stripe webhook in routers/billing.py.
# ---------------------------------------------------------------------------
_REF_RE = re.compile(r"GIQ-[A-Z0-9]{6}")
RESEND_RECEIVED_ENDPOINT = "https://api.resend.com/emails/received/{email_id}"
_SVIX_TOLERANCE_SECONDS = 300


def _verify_svix_signature(headers, raw_body: bytes) -> bool:
    """Verify a Svix-signed webhook (Resend uses Svix). Fails closed when the secret
    is unset so the endpoint can't be spoofed. Algorithm: HMAC-SHA256 over
    `{id}.{timestamp}.{body}`, base64-compared against the v1 signatures in the header."""
    secret = settings.RESEND_WEBHOOK_SECRET
    if not secret:
        logger.error("RESEND_WEBHOOK_SECRET unset — rejecting inbound webhook (fail closed).")
        return False
    svix_id = headers.get("svix-id")
    svix_ts = headers.get("svix-timestamp")
    svix_sig = headers.get("svix-signature")
    if not (svix_id and svix_ts and svix_sig):
        return False
    try:
        if abs(time.time() - int(svix_ts)) > _SVIX_TOLERANCE_SECONDS:
            logger.warning("Inbound webhook timestamp outside tolerance.")
            return False
    except ValueError:
        return False
    try:
        secret_bytes = base64.b64decode(secret.split("_", 1)[1] if "_" in secret else secret)
    except Exception:
        logger.error("RESEND_WEBHOOK_SECRET is not valid base64.")
        return False
    signed = f"{svix_id}.{svix_ts}.{raw_body.decode('utf-8')}".encode("utf-8")
    expected = base64.b64encode(hmac.new(secret_bytes, signed, hashlib.sha256).digest()).decode("utf-8")
    for part in svix_sig.split():
        sig = part.split(",", 1)[1] if "," in part else part
        if hmac.compare_digest(sig, expected):
            return True
    return False


def _match_ticket(subject: str, from_email: str | None, db: Session):
    """Find the ticket an inbound reply belongs to: by the GIQ ref in the subject
    first (covers replies to our emails), then the most recent ticket from that sender."""
    m = _REF_RE.search(subject or "")
    if m:
        t = db.query(SupportTicket).filter(SupportTicket.ref_code == m.group(0)).first()
        if t:
            return t
    if from_email:
        t = (
            db.query(SupportTicket)
            .filter(func.lower(SupportTicket.requester_email) == from_email.lower())
            .order_by(SupportTicket.created_at.desc())
            .first()
        )
        if t:
            return t
    return None


def _create_ticket_from_email(from_email: str | None, subject: str, db: Session) -> SupportTicket:
    """An inbound email with no matching ticket still opens one, so nothing is lost."""
    user = (
        db.query(User).filter(func.lower(User.email_address) == from_email.lower()).first()
        if from_email else None
    )
    ticket_id = new_id()
    t = SupportTicket(
        ticket_id=ticket_id,
        ref_code=_ref_code(ticket_id),
        user_id=user.user_id if user else None,
        requester_email=from_email,
        category="question",
        subject=(subject or "(no subject)")[:200],
        message="(Opened from an inbound email — see the conversation below.)",
        status="open",
    )
    db.add(t)
    db.flush()  # persist before the message references it
    return t


async def _fetch_received_body(email_id: str | None):
    """Best-effort fetch of the inbound email body via Resend's Receiving API (the
    webhook carries only metadata). If it fails we degrade — the admin still sees the
    subject and can open the email in the Resend dashboard. Endpoint path is isolated
    here (RESEND_RECEIVED_ENDPOINT) so it's a one-line change if Resend's API moves."""
    if not (email_id and settings.RESEND_API_KEY):
        return None, None
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                RESEND_RECEIVED_ENDPOINT.format(email_id=email_id),
                headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
            )
        if resp.status_code >= 400:
            logger.warning("Resend received-email fetch failed (%s) for %s", resp.status_code, email_id)
            return None, None
        d = resp.json()
        return d.get("text"), d.get("html")
    except Exception as e:  # noqa: BLE001
        logger.warning("Resend received-email fetch error for %s: %s", email_id, e)
        return None, None


@router.post("/webhooks/resend-inbound")
async def resend_inbound_webhook(request: Request, db: Session = Depends(get_db)):
    raw = await request.body()
    if not _verify_svix_signature(request.headers, raw):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid signature")
    try:
        event = json.loads(raw)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON")

    if event.get("type") != "email.received":
        return {"received": True, "ignored": event.get("type")}

    data = event.get("data") or {}
    email_id = data.get("email_id")

    # Idempotency — Resend/Svix retries; dedupe on the inbound email id.
    if email_id and db.query(SupportMessage).filter(SupportMessage.provider_message_id == email_id).first():
        return {"received": True, "duplicate": True}

    from_name, from_email = parseaddr(data.get("from") or "")
    from_email = (from_email or "").lower() or None
    subject = data.get("subject") or ""

    ticket = _match_ticket(subject, from_email, db) or _create_ticket_from_email(from_email, subject, db)

    text, html = await _fetch_received_body(email_id)
    body = (text or "").strip()
    if not body and not html:
        body = "(Inbound reply — open the email in the Resend dashboard for full content.)"
    attachments = [{"filename": a.get("filename")} for a in (data.get("attachments") or []) if a.get("filename")]

    db.add(SupportMessage(
        ticket_id=ticket.ticket_id,
        direction="inbound",
        author_email=from_email,
        author_name=from_name or None,
        body=body,
        body_html=html,
        attachments=attachments or None,
        provider_message_id=email_id,
    ))
    ticket.status = "open"
    ticket.updated_at = datetime.now(timezone.utc)
    try:
        db.commit()
    except Exception as e:  # noqa: BLE001
        db.rollback()
        logger.error("Failed to store inbound support message (email_id=%s): %s", email_id, e)
        raise HTTPException(status_code=500, detail="Could not store inbound message.")

    logger.info("Inbound support email stored ticket=%s from=%s", ticket.ref_code, from_email)
    return {"received": True, "ticket": ticket.ref_code}
