"""Operational control plane router.

Public:
  GET  /site-config        — what the SPA polls: maintenance (sanitized), read_only,
                             visible announcements, latest published changelog entry.
  GET  /changelog          — published "what's new" feed.

Staff (require_staff — DB is_staff check):
  GET/PUT    /admin/site-settings        — maintenance / read_only / feature_flags
  GET/POST   /admin/announcements
  PATCH/DEL  /admin/announcements/{id}
  GET/POST   /admin/changelog
  PATCH/DEL  /admin/changelog/{id}

Bootstrap (X-Admin-Key break-glass — same shared secret as billing /admin/grant-comp):
  POST /admin/set-staff   — grant/revoke users.is_staff by email (anoint the first staff,
                            then they self-serve via the console).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from config import settings
from models import get_db, User, SiteSetting, Announcement, ChangelogEntry, SupportTicket, SupportMessage
from utils.token_generation import require_staff, token_validator
from utils.email import send_email, support_reply_html
from utils import ops_state
from utils.logger import logger

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _actor(current: dict) -> Optional[str]:
    """Email of the staff user making the change (for updated_by/created_by audit)."""
    tok = (current or {}).get("regular_login_token") or {}
    return tok.get("email") or tok.get("id")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _norm_emails(vals) -> List[str]:
    """Normalize a recipient list to lowercased, trimmed, de-duped, order-preserving."""
    if not vals:
        return []
    seen, out = set(), []
    for v in vals:
        e = (str(v) or "").strip().lower()
        if e and e not in seen:
            seen.add(e)
            out.append(e)
    return out


def _announcement_visible_now(a: Announcement, now: datetime) -> bool:
    if not a.active:
        return False
    if a.starts_at and a.starts_at > now:
        return False
    if a.ends_at and a.ends_at < now:
        return False
    return True


def _ann_public(a: Announcement) -> dict:
    return {
        "id": a.id, "kind": a.kind, "title": a.title, "body": a.body,
        "dismissible": a.dismissible, "audience": a.audience,
        "link_url": a.link_url, "link_label": a.link_label,
    }


def _ann_full(a: Announcement) -> dict:
    return {
        **_ann_public(a),
        "active": a.active,
        "starts_at": a.starts_at.isoformat() if a.starts_at else None,
        "ends_at": a.ends_at.isoformat() if a.ends_at else None,
        # Recipient list is visible to staff in the console; never in public payloads.
        "target_emails": a.target_emails or [],
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "created_by": a.created_by,
    }


def _cl_public(c: ChangelogEntry) -> dict:
    return {
        "id": c.id, "version": c.version, "title": c.title, "body": c.body,
        "category": c.category, "media_url": c.media_url,
        "published_at": c.published_at.isoformat() if c.published_at else None,
    }


def _cl_full(c: ChangelogEntry) -> dict:
    return {
        **_cl_public(c),
        "published": c.published,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "created_by": c.created_by,
    }


# ---------------------------------------------------------------------------
# Public
# ---------------------------------------------------------------------------
@router.get("/site-config")
async def site_config(db: Session = Depends(get_db)):
    """Single source the SPA polls. Cheap; safe to call unauthenticated. Maintenance
    is returned sanitized (no allowlist internals)."""
    state = ops_state.get_ops_state(db)
    m = state["maintenance"]
    now = _now()
    anns = (
        db.query(Announcement)
        # 'users'-targeted announcements are excluded here (public/anonymous endpoint) and
        # served only via the authenticated /my-site-config, so recipient lists never leak.
        .filter(Announcement.active == True, Announcement.audience != "users")  # noqa: E712
        .order_by(Announcement.created_at.desc())
        .all()
    )
    # `_ann_public` carries `audience` so the SPA can hide 'authenticated' banners
    # from logged-out visitors.
    visible = [_ann_public(a) for a in anns if _announcement_visible_now(a, now)]

    latest = (
        db.query(ChangelogEntry)
        .filter(ChangelogEntry.published == True)  # noqa: E712
        .order_by(ChangelogEntry.published_at.desc().nullslast(), ChangelogEntry.created_at.desc())
        .first()
    )
    # Public/anonymous view: only report maintenance when it's SITE-WIDE (the `on` toggle with
    # no target list). Targeted maintenance is scoped per-user and reported only via the authed
    # /my-site-config, so anonymous visitors and non-targeted users keep seeing the normal site.
    site_wide = bool(m["on"]) and not (m.get("target_emails") or [])
    return {
        "maintenance": {"on": site_wide, "title": m["title"], "message": m["message"],
                        "eta": m["eta"], "media_url": m.get("media_url", "")},
        "read_only": {"on": bool(state["read_only"]["on"]), "message": state["read_only"]["message"]},
        "announcements": visible,
        "changelog_latest": ({"id": latest.id, "version": latest.version, "title": latest.title}
                             if latest else None),
    }


@router.get("/changelog")
async def changelog(db: Session = Depends(get_db)):
    rows = (
        db.query(ChangelogEntry)
        .filter(ChangelogEntry.published == True)  # noqa: E712
        .order_by(ChangelogEntry.published_at.desc().nullslast(), ChangelogEntry.created_at.desc())
        .limit(100)
        .all()
    )
    return {"entries": [_cl_public(c) for c in rows]}


@router.get("/my-site-config")
async def my_site_config(current: dict = Depends(token_validator), db: Session = Depends(get_db)):
    """Per-user overlay on the public /site-config for the signed-in caller:
      - `announcements`: targeted (audience='users') notices matched on their email.
      - `maintenance`: non-null when this account should see the maintenance page. The `on`
        toggle is the master switch; `target_emails` scopes it — with a list, only those
        accounts (this is the per-user signal the public config omits); without a list it's
        site-wide. Staff are never gated by a *scoped* maintenance.
    Kept off the public endpoint so recipient lists never reach anonymous clients."""
    tok = (current or {}).get("regular_login_token") or {}
    email = (tok.get("email") or "").strip().lower()
    is_staff = bool(tok.get("is_staff"))
    now = _now()

    anns: list = []
    if email:
        rows = (
            db.query(Announcement)
            .filter(Announcement.active == True, Announcement.audience == "users")  # noqa: E712
            .order_by(Announcement.created_at.desc())
            .all()
        )
        anns = [
            _ann_public(a) for a in rows
            if _announcement_visible_now(a, now)
            and email in {str(t).strip().lower() for t in (a.target_emails or [])}
        ]

    m = ops_state.get_ops_state(db)["maintenance"]
    targets = {str(t).strip().lower() for t in (m.get("target_emails") or [])}
    if not bool(m.get("on")):
        show_maint = False
    elif targets:
        # Scoped: only listed accounts, and never staff (they'd bypass server-side anyway).
        show_maint = bool(email) and email in targets and not is_staff
    else:
        show_maint = True  # site-wide (public config already drives this; staff get bypass bar)
    maintenance = (
        {"on": True, "title": m.get("title", ""), "message": m.get("message", ""),
         "eta": m.get("eta", ""), "media_url": m.get("media_url", "")}
        if show_maint else None
    )
    return {"announcements": anns, "maintenance": maintenance}


# ---------------------------------------------------------------------------
# Staff — site settings (maintenance / read-only / feature flags)
# ---------------------------------------------------------------------------
class MaintenanceIn(BaseModel):
    on: Optional[bool] = None
    title: Optional[str] = None
    message: Optional[str] = None
    eta: Optional[str] = None
    media_url: Optional[str] = None
    allowlist_ips: Optional[List[str]] = None
    allowlist_emails: Optional[List[str]] = None
    target_emails: Optional[List[str]] = None  # targeted/"troll" maintenance recipients


class ReadOnlyIn(BaseModel):
    on: Optional[bool] = None
    message: Optional[str] = None


class FeatureFlagsIn(BaseModel):
    signups_enabled: Optional[bool] = None
    logins_enabled: Optional[bool] = None
    pipeline_enabled: Optional[bool] = None


class SiteSettingsIn(BaseModel):
    maintenance: Optional[MaintenanceIn] = None
    read_only: Optional[ReadOnlyIn] = None
    feature_flags: Optional[FeatureFlagsIn] = None


@router.get("/admin/site-settings")
async def get_site_settings(current: dict = Depends(require_staff), db: Session = Depends(get_db)):
    """Full (unsanitized) ops state for the console — includes allowlists."""
    return ops_state.get_ops_state(db)


@router.put("/admin/site-settings")
async def put_site_settings(
    body: SiteSettingsIn,
    current: dict = Depends(require_staff),
    db: Session = Depends(get_db),
):
    actor = _actor(current)
    changed = []
    for key in ("maintenance", "read_only", "feature_flags"):
        section = getattr(body, key)
        if section is None:
            continue
        patch = section.model_dump(exclude_none=True)
        if not patch:
            continue
        if key == "maintenance" and "target_emails" in patch:
            patch["target_emails"] = _norm_emails(patch["target_emails"])
        ops_state.upsert_setting(db, key, patch, updated_by=actor)
        changed.append(key)
    logger.info("ADMIN site-settings updated by=%s keys=%s", actor, changed)
    return ops_state.get_ops_state(db)


# ---------------------------------------------------------------------------
# Staff — announcements
# ---------------------------------------------------------------------------
class AnnouncementIn(BaseModel):
    kind: str = "info"
    title: str
    body: Optional[str] = None
    active: bool = True
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    dismissible: bool = True
    audience: str = "all"  # all | authenticated | users
    link_url: Optional[str] = None
    link_label: Optional[str] = None
    target_emails: Optional[List[str]] = None  # used when audience='users'


class AnnouncementPatch(BaseModel):
    kind: Optional[str] = None
    title: Optional[str] = None
    body: Optional[str] = None
    active: Optional[bool] = None
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    dismissible: Optional[bool] = None
    audience: Optional[str] = None
    link_url: Optional[str] = None
    link_label: Optional[str] = None
    target_emails: Optional[List[str]] = None


@router.get("/admin/announcements")
async def list_announcements(current: dict = Depends(require_staff), db: Session = Depends(get_db)):
    rows = db.query(Announcement).order_by(Announcement.created_at.desc()).all()
    return {"announcements": [_ann_full(a) for a in rows]}


@router.post("/admin/announcements")
async def create_announcement(
    body: AnnouncementIn, current: dict = Depends(require_staff), db: Session = Depends(get_db)
):
    data = body.model_dump()
    data["target_emails"] = _norm_emails(data.get("target_emails"))
    a = Announcement(**data, created_by=_actor(current))
    db.add(a)
    db.commit()
    db.refresh(a)
    return _ann_full(a)


@router.patch("/admin/announcements/{ann_id}")
async def update_announcement(
    ann_id: str, body: AnnouncementPatch, current: dict = Depends(require_staff), db: Session = Depends(get_db)
):
    a = db.query(Announcement).filter(Announcement.id == ann_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Announcement not found")
    updates = body.model_dump(exclude_none=True)
    if "target_emails" in updates:
        updates["target_emails"] = _norm_emails(updates["target_emails"])
    for field, val in updates.items():
        setattr(a, field, val)
    db.commit()
    db.refresh(a)
    return _ann_full(a)


@router.delete("/admin/announcements/{ann_id}")
async def delete_announcement(
    ann_id: str, current: dict = Depends(require_staff), db: Session = Depends(get_db)
):
    a = db.query(Announcement).filter(Announcement.id == ann_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Announcement not found")
    db.delete(a)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Staff — changelog
# ---------------------------------------------------------------------------
class ChangelogIn(BaseModel):
    version: Optional[str] = None
    title: str
    body: Optional[str] = None
    category: Optional[str] = None
    media_url: Optional[str] = None
    published: bool = False


class ChangelogPatch(BaseModel):
    version: Optional[str] = None
    title: Optional[str] = None
    body: Optional[str] = None
    category: Optional[str] = None
    media_url: Optional[str] = None
    published: Optional[bool] = None


def _apply_published_at(entry: ChangelogEntry) -> None:
    """Stamp published_at the first time an entry flips to published; clear if unpublished."""
    if entry.published and entry.published_at is None:
        entry.published_at = _now()
    if not entry.published:
        entry.published_at = None


@router.get("/admin/changelog")
async def list_changelog(current: dict = Depends(require_staff), db: Session = Depends(get_db)):
    rows = db.query(ChangelogEntry).order_by(ChangelogEntry.created_at.desc()).all()
    return {"entries": [_cl_full(c) for c in rows]}


@router.post("/admin/changelog")
async def create_changelog(
    body: ChangelogIn, current: dict = Depends(require_staff), db: Session = Depends(get_db)
):
    c = ChangelogEntry(**body.model_dump(), created_by=_actor(current))
    _apply_published_at(c)
    db.add(c)
    db.commit()
    db.refresh(c)
    return _cl_full(c)


@router.patch("/admin/changelog/{entry_id}")
async def update_changelog(
    entry_id: str, body: ChangelogPatch, current: dict = Depends(require_staff), db: Session = Depends(get_db)
):
    c = db.query(ChangelogEntry).filter(ChangelogEntry.id == entry_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Changelog entry not found")
    for field, val in body.model_dump(exclude_none=True).items():
        setattr(c, field, val)
    _apply_published_at(c)
    db.commit()
    db.refresh(c)
    return _cl_full(c)


@router.delete("/admin/changelog/{entry_id}")
async def delete_changelog(
    entry_id: str, current: dict = Depends(require_staff), db: Session = Depends(get_db)
):
    c = db.query(ChangelogEntry).filter(ChangelogEntry.id == entry_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Changelog entry not found")
    db.delete(c)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Staff — admins manage admins (in-console). require_staff-gated, so an existing
# admin promotes/demotes others. Self-revoke is blocked to avoid lock-out; the
# X-Admin-Key bootstrap below remains the break-glass/recovery path.
# ---------------------------------------------------------------------------
class StaffGrantIn(BaseModel):
    email: str
    is_staff: bool = True


@router.get("/admin/staff")
async def list_staff(current: dict = Depends(require_staff), db: Session = Depends(get_db)):
    rows = db.query(User).filter(User.is_staff == True).order_by(User.email_address).all()  # noqa: E712
    return {"staff": [
        {"user_id": u.user_id, "email": u.email_address, "full_name": getattr(u, "full_name", None)}
        for u in rows
    ]}


@router.post("/admin/staff")
async def grant_staff(body: StaffGrantIn, current: dict = Depends(require_staff), db: Session = Depends(get_db)):
    actor_email = (((current or {}).get("regular_login_token") or {}).get("email") or "").lower()
    target_email = body.email.strip().lower()
    if actor_email and actor_email == target_email and not body.is_staff:
        raise HTTPException(
            status_code=400,
            detail="You can't revoke your own staff access — ask another admin, or use the break-glass key.",
        )
    user = db.query(User).filter(func.lower(User.email_address) == target_email).first()
    if not user:
        raise HTTPException(status_code=404, detail="No user with that email — they must sign up first.")
    user.is_staff = body.is_staff
    db.commit()
    logger.info("ADMIN staff change by=%s target=%s is_staff=%s", actor_email, target_email, body.is_staff)
    return {"email": user.email_address, "is_staff": user.is_staff}


# ---------------------------------------------------------------------------
# Per-firm client email templates (staff-managed). Admins pick an org, edit the
# copy fields for the questionnaire invite/reminder; GroundedIQ branding + the
# email shell are NEVER overridable (rendered server-side). Raw HTML is not
# accepted — only the named text fields — so a template can't break or de-brand.
# ---------------------------------------------------------------------------
_EMAIL_TEMPLATE_KEYS = ("questionnaire_invite", "questionnaire_reminder")


class FirmEmailTemplateIn(BaseModel):
    subject: Optional[str] = None
    heading: Optional[str] = None
    intro: Optional[str] = None
    button_label: Optional[str] = None
    signoff: Optional[str] = None


@router.get("/admin/firms")
async def admin_list_firms(search: Optional[str] = None, current: dict = Depends(require_staff), db: Session = Depends(get_db)):
    """Searchable firm list for the template-manager dropdown."""
    from database_scripts import list_firms
    return {"firms": list_firms(search, db)}


@router.get("/admin/firm-email-templates/{firm_id}")
async def admin_get_firm_email_templates(firm_id: str, current: dict = Depends(require_staff), db: Session = Depends(get_db)):
    """Return, per template key, the firm's saved overrides + the GroundedIQ defaults
    (so the UI shows defaults as placeholders the admin can override)."""
    from database_scripts import get_firm_email_template_fields
    from utils.email import DEFAULT_QUESTIONNAIRE_FIELDS
    out = {}
    for key in _EMAIL_TEMPLATE_KEYS:
        out[key] = {
            "defaults": DEFAULT_QUESTIONNAIRE_FIELDS[key],
            "override": get_firm_email_template_fields(firm_id, key, db),
        }
    return {"firm_id": firm_id, "templates": out}


@router.put("/admin/firm-email-templates/{firm_id}/{template_key}")
async def admin_set_firm_email_template(
    firm_id: str, template_key: str, body: FirmEmailTemplateIn,
    current: dict = Depends(require_staff), db: Session = Depends(get_db),
):
    """Upsert a firm's override text for one template key. Empty fields fall back to
    the GroundedIQ default at render time."""
    from database_scripts import set_firm_email_template
    if template_key not in _EMAIL_TEMPLATE_KEYS:
        raise HTTPException(status_code=400, detail=f"Unknown template key. Allowed: {_EMAIL_TEMPLATE_KEYS}")
    saved = set_firm_email_template(firm_id, template_key, body.model_dump(exclude_none=False), db)
    logger.info("ADMIN firm-email-template firm=%s key=%s by=%s", firm_id, template_key, _actor(current))
    return {"firm_id": firm_id, "template_key": template_key, "override": saved}


# ---------------------------------------------------------------------------
# Bootstrap — grant/revoke staff via the shared X-Admin-Key (break-glass).
# Restrict /admin/* to your IP at the Cloudflare edge as well (defense in depth).
# ---------------------------------------------------------------------------
class SetStaffIn(BaseModel):
    email: str
    is_staff: bool = True


@router.post("/admin/set-staff")
async def set_staff(
    body: SetStaffIn, x_admin_key: str = Header(...), db: Session = Depends(get_db)
):
    if not settings.ADMIN_SECRET_KEY or x_admin_key != settings.ADMIN_SECRET_KEY:
        raise HTTPException(status_code=403, detail="Forbidden")
    user = db.query(User).filter(User.email_address == body.email.lower()).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_staff = body.is_staff
    db.commit()
    logger.info("ADMIN set-staff email=%s is_staff=%s", body.email, body.is_staff)
    return {"email": user.email_address, "is_staff": user.is_staff}


# ---------------------------------------------------------------------------
# Staff — Help & Support inbox. Staff read submitted tickets + the email thread,
# reply from the panel (sent via Resend; the user's reply threads back via the
# inbound webhook in routers/support.py), and resolve.
# ---------------------------------------------------------------------------
_SUPPORT_STATUSES = ("open", "resolved")


def _support_msg(m: SupportMessage) -> dict:
    return {
        "message_id": m.message_id,
        "direction": m.direction,
        "author_email": m.author_email,
        "author_name": m.author_name,
        "body": m.body,
        "body_html": m.body_html,
        "attachments": m.attachments or [],
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


def _ticket_row(t: SupportTicket) -> dict:
    return {
        "ticket_id": t.ticket_id,
        "ref_code": t.ref_code,
        "category": t.category,
        "subject": t.subject,
        "status": t.status,
        "requester_email": t.requester_email,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if getattr(t, "updated_at", None) else None,
    }


def _ticket_detail(t: SupportTicket) -> dict:
    return {
        **_ticket_row(t),
        "message": t.message,
        "screenshots": [k for k in (t.screenshot_path or "").split(",") if k],
    }


@router.get("/admin/support/tickets")
async def list_support_tickets(
    status_filter: Optional[str] = Query(None, alias="status"),
    current: dict = Depends(require_staff),
    db: Session = Depends(get_db),
):
    q = db.query(SupportTicket)
    if status_filter in _SUPPORT_STATUSES:
        q = q.filter(SupportTicket.status == status_filter)
    rows = (
        q.order_by(SupportTicket.updated_at.desc().nullslast(), SupportTicket.created_at.desc())
        .limit(200)
        .all()
    )
    return {"tickets": [_ticket_row(t) for t in rows]}


@router.get("/admin/support/tickets/{ticket_id}")
async def get_support_ticket(
    ticket_id: str, current: dict = Depends(require_staff), db: Session = Depends(get_db)
):
    t = db.query(SupportTicket).filter(SupportTicket.ticket_id == ticket_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Ticket not found")
    msgs = (
        db.query(SupportMessage)
        .filter(SupportMessage.ticket_id == ticket_id)
        .order_by(SupportMessage.created_at.asc())
        .all()
    )
    return {"ticket": _ticket_detail(t), "messages": [_support_msg(m) for m in msgs]}


class SupportReplyIn(BaseModel):
    message: str


@router.post("/admin/support/tickets/{ticket_id}/reply")
async def reply_support_ticket(
    ticket_id: str, body: SupportReplyIn,
    current: dict = Depends(require_staff), db: Session = Depends(get_db),
):
    t = db.query(SupportTicket).filter(SupportTicket.ticket_id == ticket_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Ticket not found")
    msg_text = (body.message or "").strip()
    if not msg_text:
        raise HTTPException(status_code=400, detail="Reply cannot be empty.")
    if not t.requester_email:
        raise HTTPException(status_code=400, detail="This ticket has no requester email to reply to.")

    name = None
    if t.user_id:
        u = db.query(User).filter(User.user_id == t.user_id).first()
        name = getattr(u, "full_name", None) if u else None
    name = name or t.requester_email.split("@")[0]

    # reply_to = the support inbox, so the user's reply lands back on the inbound webhook.
    sent = await send_email(
        to=t.requester_email,
        subject=f"Re: [{t.ref_code}] {t.subject}"[:200],
        html=support_reply_html(name, t.ref_code, msg_text),
        reply_to=settings.SUPPORT_INBOX,
    )

    db.add(SupportMessage(
        ticket_id=t.ticket_id,
        direction="outbound",
        author_email=_actor(current),
        body=msg_text,
    ))
    t.status = "open"
    t.updated_at = _now()
    db.commit()
    logger.info("ADMIN support reply ticket=%s by=%s sent=%s", t.ref_code, _actor(current), sent)
    return {"ok": True, "email_sent": sent}


class SupportStatusIn(BaseModel):
    status: str


@router.post("/admin/support/tickets/{ticket_id}/status")
async def set_support_status(
    ticket_id: str, body: SupportStatusIn,
    current: dict = Depends(require_staff), db: Session = Depends(get_db),
):
    if body.status not in _SUPPORT_STATUSES:
        raise HTTPException(status_code=400, detail=f"Status must be one of {_SUPPORT_STATUSES}")
    t = db.query(SupportTicket).filter(SupportTicket.ticket_id == ticket_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Ticket not found")
    t.status = body.status
    t.updated_at = _now()
    db.commit()
    return {"ok": True, "status": t.status}
