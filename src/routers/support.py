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
import io
import os

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from config import settings
from models import get_db, SupportTicket, User
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
