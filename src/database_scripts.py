import models
from models import get_db
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from p_model_type import Registration_login
from sqlalchemy import and_, func
from utils.token_generation import hash_passwords
from utils.report_sections import parse_sections
from utils.email_validation import is_disposable_email
from config import settings
from fastapi import HTTPException, status
from utils.logger import logger
from datetime import datetime, timezone, timedelta
import copy
import json
import uuid
from utils.ids import new_id
from typing import Optional

class UserCreationError(Exception):
    pass

async def create_user(user_data:dict,provider:str, db:Session):
    # {'id': '106124317363210854486', 'email': '@gmail.com', 'verified_email': True, 'name': 'full name', 'given_name': 'first name', 'family_name': 'last name', 'picture': 'https://lh3.googleusercontent.com/a/ACg8ocKaB3SgzhN1nS059s7D1re6z0eTnG6wtUDl5A695G-8Akhvq5GD'}
    # {'email': '123@123.com', 'given_name': '123', 'family_name': '456', 'name': '123 456', 'password': 'string', 'id': None, 'verified_email': False, 'picture': None, 'provider': 'Local'}
    if not user_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail="Required details not provided")
    try:
        query = db.query(models.User).filter(and_(models.User.email_address == user_data["email"], models.User.provider == provider))
        user_details = query.first()
        if user_details and user_details.provider == "Local":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Record already Exists, try logging into the account")
    except SQLAlchemyError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"unable to connect to DB {e}")
    
    if not user_details:
        # Google's /userinfo only guarantees id + email + verified_email; given_name,
        # family_name, name and picture are optional and ARE omitted for some profiles
        # (e.g. accounts with no surname). first/last/full_name are NOT NULL columns, so
        # derive non-null fallbacks instead of indexing (a bare user_data["family_name"]
        # crashed new-account signup with KeyError). The Local path always sets these keys,
        # so .get() is behaviour-preserving there.
        given = (user_data.get("given_name") or "").strip()
        family = (user_data.get("family_name") or "").strip()
        full = (user_data.get("name") or "").strip() or f"{given} {family}".strip() or user_data["email"].split("@")[0]
        user_details = models.User(
            oauth_id = user_data.get("id"),
            email_address = user_data["email"],
            first_name = given or full,
            last_name = family,
            verified_email = user_data.get("verified_email", False),
            full_name = full,
            picture = user_data.get("picture"),
            provider = provider,
            company = user_data.get("company"),
            subscription_tier = "free",
            subscription_status = "active",
        )
        try:
            db.add(user_details)
            db.commit()
            db.refresh(user_details)

        except SQLAlchemyError as e:
            db.rollback()
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,detail=f"unable to create details: {str(e.args), str(e.code)}")

        # Auto-assign a 1-person firm (Bet 3). Failure here is non-fatal — the user
        # still gets a working account, but firm-admin features will no-op until
        # a firm is assigned manually or via the migration backfill.
        try:
            ensure_firm_for_new_user(user_details.user_id, db)
            db.refresh(user_details)
        except Exception as fe:  # noqa: BLE001
            logger.error(f"ensure_firm_for_new_user failed at signup for {user_details.user_id}: {fe}")

        if user_details.provider == "Local":
            h_pass = hash_passwords(password=user_data["password"]) 
            password_details = models.LoginDetails(
                user_id = user_details.user_id,
                hashed_password = h_pass
            )
            try:
                db.add(password_details)
                db.commit()
            except SQLAlchemyError as e:
                db.rollback() 
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"unable to create details: {str(e)}")
        return user_details
    return user_details

async def get_or_create_oauth_user(user_data: dict, provider: str, db: Session, *, ip=None, user_agent=None, device_id=None):
    """Login path for social providers (Google/GitHub/Microsoft): one human = one
    account, keyed by VERIFIED email. If a user already exists for this email — under
    ANY provider, including a Local password account — we sign them into THAT account
    (link by verified email) instead of spawning a duplicate row with its own firm/
    projects. Only when no account exists for the email do we create one (reusing
    create_user, so firm auto-assignment etc. stay identical).

    Safe because every caller passes a provider-verified email (the OAuth classes reject
    accounts without one). create_user still owns the Local /registration path unchanged."""
    if not user_data or not user_data.get("email"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Required details not provided")
    email = user_data["email"].strip().lower()
    try:
        # Case-insensitive match: Local signup stores the email as typed (e.g.
        # "Ada@Acme.com"), so an exact == on the lowercased OAuth email would miss it
        # and spawn a duplicate account instead of linking. Email is the identity.
        existing = db.query(models.User).filter(func.lower(models.User.email_address) == email).first()
    except SQLAlchemyError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"unable to connect to DB {e}")
    if existing:
        # Pre-hijack guard, then record this provider as a linked identity.
        _neutralize_unverified_local(existing, db)
        record_identity(existing.user_id, provider, user_data.get("id"), email, db)
        return existing
    # Creating a NEW account → block disposable/throwaway emails. Matters most for GitHub,
    # where a user can attach an arbitrary verified email (Google/Microsoft are their own
    # domains). Existing-account links above are never blocked.
    if is_disposable_email(email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please sign up with a permanent (non-disposable) email address.",
        )
    # create_user's (email, provider) duplicate guard can't fire here — no row has this email.
    new_user = await create_user(user_data=user_data, provider=provider, db=db)
    record_identity(new_user.user_id, provider, user_data.get("id"), email, db)
    record_signup_event(new_user, email, ip, device_id, user_agent, provider, db)
    return new_user


def record_signup_event(user, email, ip, device_id, user_agent, provider, db):
    """Audit-log an account creation and soft-flag it when device/IP signup velocity over
    the last 24h exceeds the configured thresholds. Flag-only — NEVER blocks (the device/IP
    signal is spoofable). Best-effort: failures are logged, not raised, so abuse tracking
    can't break signup."""
    try:
        since = datetime.now(timezone.utc) - timedelta(hours=24)
        flagged = False
        if device_id:
            dev_count = db.query(models.SignupEvent).filter(
                models.SignupEvent.device_id == device_id,
                models.SignupEvent.created_at >= since,
            ).count()
            if dev_count >= settings.SIGNUP_MAX_PER_DEVICE_PER_DAY:
                flagged = True
        if ip:
            ip_count = db.query(models.SignupEvent).filter(
                models.SignupEvent.ip == ip,
                models.SignupEvent.created_at >= since,
            ).count()
            if ip_count >= settings.SIGNUP_MAX_PER_IP_PER_DAY:
                flagged = True
        event = models.SignupEvent(
            user_id=getattr(user, "user_id", None),
            email=email,
            ip=ip,
            device_id=device_id,
            user_agent=((user_agent or "")[:500] or None),
            provider=provider,
            flagged=flagged,
        )
        db.add(event)
        db.commit()
        if flagged:
            logger.warning(
                f"Flagged signup (velocity): user={getattr(user, 'user_id', None)} "
                f"ip={ip} device={device_id} provider={provider}"
            )
        return event
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"record_signup_event failed: {e}")
        return None


def _neutralize_unverified_local(user, db) -> None:
    """Account pre-hijacking guard. A verified OAuth login matched an EXISTING account;
    if that account was never verified, the OAuth owner (who proved control of the
    mailbox) is the rightful owner. Mark it verified and revoke any unverified local
    password, so a password an attacker pre-registered on the victim's email can't
    survive the real owner signing in. Verified accounts are left untouched — a
    legitimate user who confirmed their email keeps their password when they link OAuth."""
    if user.verified_email:
        return
    try:
        login_row = db.query(models.LoginDetails).filter(
            models.LoginDetails.user_id == user.user_id
        ).first()
        if login_row:
            db.delete(login_row)
            logger.warning(
                f"Revoked unverified local password for user {user.user_id} on verified OAuth takeover"
            )
        user.verified_email = True
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"_neutralize_unverified_local failed for {user.user_id}: {e}")


def record_identity(user_id: str, provider: str, provider_user_id, email, db) -> Optional[object]:
    """Upsert the (user, provider) login identity — one row per provider per user. Best
    effort: identity tracking must never block a login, so failures are logged, not raised."""
    try:
        existing = db.query(models.UserIdentity).filter(
            models.UserIdentity.user_id == user_id,
            models.UserIdentity.provider == provider,
        ).first()
        if existing:
            changed = False
            if provider_user_id and existing.provider_user_id != str(provider_user_id):
                existing.provider_user_id = str(provider_user_id); changed = True
            if email and existing.email != email:
                existing.email = email; changed = True
            if changed:
                db.commit()
            return existing
        ident = models.UserIdentity(
            user_id=user_id,
            provider=provider,
            provider_user_id=str(provider_user_id) if provider_user_id else None,
            email=(email or None),
        )
        db.add(ident)
        db.commit()
        return ident
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"record_identity failed for {user_id}/{provider}: {e}")
        return None


def get_linked_identities(user_id: str, db) -> list:
    """Linked login methods for a user (for a Connected-accounts surface)."""
    try:
        rows = db.query(models.UserIdentity).filter(
            models.UserIdentity.user_id == user_id
        ).order_by(models.UserIdentity.created_at).all()
    except SQLAlchemyError as e:
        logger.error(f"get_linked_identities failed for {user_id}: {e}")
        return []
    return [
        {
            "provider": r.provider,
            "email": r.email,
            "linked_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]

def get_user_details(email_address:str, db:Session):
    try:
        query = db.query(models.User.email_address,
                        models.User.user_id,
                        models.User.first_name,
                        models.User.last_name,
                        models.User.verified_email,
                        models.User.provider,
                        models.LoginDetails.hashed_password,
                        models.LoginDetails.id
                        ).join(
                            models.LoginDetails,
                            models.User.user_id == models.LoginDetails.user_id) 
        # Match Local accounts case-insensitively, REGARDLESS of verification status.
        # (The old `verified_email == "False"` clause excluded verified users, so once the
        # email-verification gate flipped verified_email=true, login could no longer find
        # them. Verification is enforced by require_verified_email/ProtectedRoute, not here.)
        record = query.filter(and_(
            models.User.provider == "Local",
            func.lower(models.User.email_address) == (email_address or "").strip().lower(),
        )).first()
    except SQLAlchemyError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Something wrong with our service, please try again later")
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Details not found, please register your account")
    return record


async def user_documents(doc_data:dict, db:Session) -> dict:
    if not doc_data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No document data found with valid user_id found")
    document_details = models.UserDocuments(
        user_id = doc_data["user_id"],
        document_path = doc_data["document_path"]
    )
    try:
        db.add(document_details)
        db.commit()
        db.refresh(document_details)
        return {"document_id":document_details.document_id,"document_path":document_details.document_path,"user_id":document_details.user_id}
    except SQLAlchemyError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"unable to create document data {str(e)}")
    
async def get_summary_report(chat_history_id:str, db:Session)-> dict:
    """Return the ACTIVE report version for a chat — the user-selected default
    when one is set, otherwise the newest. This is the single source of truth the
    chat answers from, so marking a version default makes every answer (and the
    re-embedded vector store) reflect that version instead of the latest."""
    try:
        base = db.query(models.ReportVersions).filter(models.ReportVersions.chat_history_id == chat_history_id)
        record = base.filter(models.ReportVersions.is_default == True).order_by(models.ReportVersions.created_at.desc()).first()
        if not record:
            record = base.order_by(models.ReportVersions.created_at.desc()).first()
        return record
    except SQLAlchemyError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error occured with the DB, chat history id: {chat_history_id}, error: {str(e)}")


# ============================================================
# A6 — PRE-MORTEM (adversarial-persona objections cache)
# ============================================================

def _active_report_version_row(chat_history_id: str, db: Session):
    """The ACTIVE report_version row: user-selected default if set, else newest.
    Single source of truth shared by get_summary_report and the pre-mortem helpers
    so the panel grounds on (and writes to) the SAME version the chat answers from —
    otherwise positional pre-mortem evidence ids would drift between read and write."""
    base = db.query(models.ReportVersions).filter(
        models.ReportVersions.chat_history_id == chat_history_id
    )
    row = base.filter(models.ReportVersions.is_default == True).order_by(  # noqa: E712
        models.ReportVersions.created_at.desc()
    ).first()
    if not row:
        row = base.order_by(models.ReportVersions.created_at.desc()).first()
    return row


async def get_pre_mortem(chat_history_id: str, db: Session) -> Optional[dict]:
    """
    Return the cached pre_mortem JSON from the ACTIVE report_version of this
    chat, or None if no report exists yet, or None if pre_mortem hasn't been
    generated yet for that version.
    """
    try:
        record = _active_report_version_row(chat_history_id, db)
        if not record:
            return None
        return copy.deepcopy(record.pre_mortem) if record.pre_mortem else None
    except SQLAlchemyError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error reading pre_mortem: {str(e)}"
        )


async def save_pre_mortem(chat_history_id: str, pre_mortem: dict, db: Session) -> None:
    """
    Persist pre_mortem onto the ACTIVE report_version row for this chat.
    No locking — last writer wins (acceptable: cost of a duplicate write is
    one wasted LLM call already paid upstream).
    """
    try:
        record = _active_report_version_row(chat_history_id, db)
        if not record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No report_version found for chat {chat_history_id}"
            )
        record.pre_mortem = pre_mortem
        flag_modified(record, "pre_mortem")
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error saving pre_mortem: {str(e)}"
        )


async def get_report_version_id(chat_history_id: str, db: Session) -> Optional[str]:
    """Return the ACTIVE report_version_id for this chat, or None."""
    try:
        record = _active_report_version_row(chat_history_id, db)
        return record.report_version_id if record else None
    except SQLAlchemyError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error reading report_version_id: {str(e)}"
        )


# ============================================================
# PENDING CHANGES MANAGEMENT (Phase 1 - Hybrid Approach)
# ============================================================

# Section dependency graph - defines which sections are affected by changes
SECTION_DEPENDENCIES = {
    "modify_requirements": ["requirements", "architecture", "estimates", "executive_summary"],
    "modify_architecture": ["architecture", "components", "risks", "estimates", "executive_summary"],
    "correct_assumptions": ["assumptions", "architecture", "risks", "estimates"],
    "improve_section": [],  # Affected sections are specified dynamically based on user request
}

def get_affected_sections(action_type: str) -> list:
    """Get list of sections affected by a change type"""
    return SECTION_DEPENDENCIES.get(action_type, ["general"])


async def get_pending_changes(chat_history_id: str, db: Session) -> list:
    """
    Get all pending changes for a report.

    Args:
        chat_history_id: The chat history ID
        db: Database session

    Returns:
        List of pending change objects
    """
    try:
        # Expire all to ensure we get fresh data from DB
        db.expire_all()

        record = db.query(models.ReportVersions).filter(
            models.ReportVersions.chat_history_id == chat_history_id
        ).order_by(models.ReportVersions.created_at.desc()).first()

        if not record:
            return []

        # Return a copy to avoid mutation issues
        return copy.deepcopy(record.pending_changes) if record.pending_changes else []
    except SQLAlchemyError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving pending changes: {str(e)}"
        )


async def add_pending_change(chat_history_id: str, change: dict, db: Session) -> dict:
    """
    Add a pending change to a report.

    Args:
        chat_history_id: The chat history ID
        change: Change object with type, user_request, affected_sections, etc.
        db: Database session

    Returns:
        Updated pending changes list
    """
    try:
        record = db.query(models.ReportVersions).filter(
            models.ReportVersions.chat_history_id == chat_history_id
        ).order_by(models.ReportVersions.created_at.desc()).first()

        if not record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No report found for chat_history_id: {chat_history_id}"
            )

        # IMPORTANT: Create a deep copy of the existing changes
        # SQLAlchemy doesn't detect in-place mutations of JSON columns
        current_changes = copy.deepcopy(record.pending_changes) if record.pending_changes else []

        # Check for duplicate content to prevent tracking same change twice
        new_request = change.get("user_request", "").lower().strip()
        if new_request:
            for existing in current_changes:
                existing_request = existing.get("user_request", "").lower().strip()
                if existing_request == new_request:
                    # Exact duplicate - return existing without adding
                    logger.info(f"Skipping duplicate change: {new_request[:50]}...")
                    return {
                        "status": "duplicate",
                        "pending_changes": current_changes,
                        "change_id": existing.get("id", "CHG-XXX"),
                        "message": f"This change already exists as {existing.get('id')}"
                    }
                # Also check for high similarity (Jaccard > 0.8)
                new_words = set(new_request.split())
                existing_words = set(existing_request.split())
                if new_words and existing_words:
                    intersection = len(new_words & existing_words)
                    union = len(new_words | existing_words)
                    similarity = intersection / union if union > 0 else 0
                    if similarity > 0.8:
                        logger.info(f"Skipping highly similar change (similarity={similarity:.2f}): {new_request[:50]}...")
                        return {
                            "status": "similar",
                            "pending_changes": current_changes,
                            "change_id": existing.get("id", "CHG-XXX"),
                            "message": f"A very similar change already exists as {existing.get('id')}"
                        }

        # Add change ID if not present
        if "id" not in change:
            change["id"] = f"CHG-{len(current_changes) + 1:03d}"

        # Add the new change (to the copy)
        current_changes.append(change)

        # Assign the new list to the record
        record.pending_changes = current_changes

        # IMPORTANT: Explicitly mark the JSON column as modified
        # This tells SQLAlchemy that the column needs to be included in the UPDATE
        flag_modified(record, "pending_changes")

        db.commit()
        db.refresh(record)

        # Verify the save was successful by re-reading
        verification = db.query(models.ReportVersions).filter(
            models.ReportVersions.report_version_id == record.report_version_id
        ).first()

        if verification:
            actual_changes = verification.pending_changes or []
            if len(actual_changes) != len(current_changes):
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Change tracking verification failed: expected {len(current_changes)}, got {len(actual_changes)}"
                )

        return {"status": "success", "pending_changes": current_changes, "change_id": change["id"]}
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error adding pending change: {str(e)}"
        )


async def clear_pending_changes(chat_history_id: str, db: Session) -> dict:
    """
    Clear all pending changes for a report (after regeneration).

    Args:
        chat_history_id: The chat history ID
        db: Database session

    Returns:
        Status dict
    """
    try:
        record = db.query(models.ReportVersions).filter(
            models.ReportVersions.chat_history_id == chat_history_id
        ).order_by(models.ReportVersions.created_at.desc()).first()

        if not record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No report found for chat_history_id: {chat_history_id}"
            )

        cleared_count = len(record.pending_changes or [])
        record.pending_changes = []

        # Explicitly mark as modified for SQLAlchemy
        flag_modified(record, "pending_changes")

        db.commit()
        db.refresh(record)

        return {"status": "success", "cleared_count": cleared_count}
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error clearing pending changes: {str(e)}"
        )


async def remove_pending_change(chat_history_id: str, change_id: str, db: Session) -> dict:
    """
    Remove a specific pending change by its ID.
    Used for conflict resolution when user chooses to discard a change.

    Args:
        chat_history_id: The chat history ID
        change_id: The ID of the change to remove (e.g., "CHG-001")
        db: Database session

    Returns:
        Status dict with remaining changes
    """
    try:
        db.expire_all()

        record = db.query(models.ReportVersions).filter(
            models.ReportVersions.chat_history_id == chat_history_id
        ).order_by(models.ReportVersions.created_at.desc()).first()

        if not record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No report found for chat_history_id: {chat_history_id}"
            )

        current_changes = copy.deepcopy(record.pending_changes) if record.pending_changes else []

        # Find and remove the change with matching ID
        original_count = len(current_changes)
        current_changes = [c for c in current_changes if c.get("id") != change_id]

        if len(current_changes) == original_count:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Change {change_id} not found in pending changes"
            )

        # Update the record
        record.pending_changes = current_changes
        flag_modified(record, "pending_changes")

        db.commit()
        db.refresh(record)

        return {
            "status": "success",
            "removed_change_id": change_id,
            "remaining_changes": current_changes,
            "remaining_count": len(current_changes)
        }
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error removing pending change: {str(e)}"
        )


async def update_pending_change(chat_history_id: str, change_id: str, updates: dict, db: Session) -> dict:
    """
    Update a specific pending change.
    Used when user wants to modify a tracked change.

    Args:
        chat_history_id: The chat history ID
        change_id: The ID of the change to update
        updates: Dict of fields to update
        db: Database session

    Returns:
        Status dict with updated change
    """
    try:
        db.expire_all()

        record = db.query(models.ReportVersions).filter(
            models.ReportVersions.chat_history_id == chat_history_id
        ).order_by(models.ReportVersions.created_at.desc()).first()

        if not record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No report found for chat_history_id: {chat_history_id}"
            )

        current_changes = copy.deepcopy(record.pending_changes) if record.pending_changes else []

        # Find and update the change
        change_found = False
        for change in current_changes:
            if change.get("id") == change_id:
                change.update(updates)
                change_found = True
                break

        if not change_found:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Change {change_id} not found in pending changes"
            )

        # Update the record
        record.pending_changes = current_changes
        flag_modified(record, "pending_changes")

        db.commit()
        db.refresh(record)

        return {
            "status": "success",
            "updated_change_id": change_id,
            "pending_changes": current_changes
        }
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating pending change: {str(e)}"
        )


async def get_last_pending_change(chat_history_id: str, db: Session) -> dict:
    """
    Get the most recent pending change for undo operations.

    Args:
        chat_history_id: The chat history ID
        db: Database session

    Returns:
        The last pending change or None if no pending changes
    """
    try:
        db.expire_all()

        record = db.query(models.ReportVersions).filter(
            models.ReportVersions.chat_history_id == chat_history_id
        ).order_by(models.ReportVersions.created_at.desc()).first()

        if not record or not record.pending_changes:
            return None

        # Return the last change (most recently added)
        pending_changes = record.pending_changes
        if pending_changes:
            return pending_changes[-1]
        return None
    except SQLAlchemyError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting last pending change: {str(e)}"
        )


async def remove_last_pending_change(chat_history_id: str, db: Session) -> dict:
    """
    Remove the most recent pending change (undo last change).

    Args:
        chat_history_id: The chat history ID
        db: Database session

    Returns:
        Status dict with removed change and remaining changes
    """
    try:
        db.expire_all()

        record = db.query(models.ReportVersions).filter(
            models.ReportVersions.chat_history_id == chat_history_id
        ).order_by(models.ReportVersions.created_at.desc()).first()

        if not record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No report found for chat_history_id: {chat_history_id}"
            )

        current_changes = copy.deepcopy(record.pending_changes) if record.pending_changes else []

        if not current_changes:
            return {
                "status": "no_changes",
                "message": "No pending changes to undo",
                "remaining_changes": [],
                "remaining_count": 0
            }

        # Remove the last change
        removed_change = current_changes.pop()

        # Update the record
        record.pending_changes = current_changes
        flag_modified(record, "pending_changes")

        db.commit()
        db.refresh(record)

        return {
            "status": "success",
            "removed_change": removed_change,
            "remaining_changes": current_changes,
            "remaining_count": len(current_changes)
        }
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error removing last pending change: {str(e)}"
        )


def detect_conflicts(pending_changes: list) -> list:
    """
    Detect conflicting changes in the pending changes list.

    Conflicts are detected when:
    - Same section is modified multiple times with potentially contradictory changes
    - Architecture changes that contradict each other (e.g., "use Azure" then "use AWS")

    Args:
        pending_changes: List of pending change objects

    Returns:
        List of conflict objects with details
    """
    conflicts = []

    if not pending_changes or len(pending_changes) < 2:
        return conflicts

    # Keywords that indicate potential conflicts
    cloud_providers = ["azure", "aws", "gcp", "google cloud", "alibaba"]
    databases = ["postgresql", "mysql", "mongodb", "dynamodb", "cosmos", "redis", "sqlite"]

    # Track changes by type for conflict detection
    architecture_changes = [c for c in pending_changes if c.get("type") == "modify_architecture"]

    # Check for cloud provider conflicts
    for i, change1 in enumerate(architecture_changes):
        request1 = change1.get("user_request", "").lower()
        providers_in_1 = [p for p in cloud_providers if p in request1]

        for j, change2 in enumerate(architecture_changes[i+1:], i+1):
            request2 = change2.get("user_request", "").lower()
            providers_in_2 = [p for p in cloud_providers if p in request2]

            # If both mention different providers, flag as potential conflict
            if providers_in_1 and providers_in_2 and set(providers_in_1) != set(providers_in_2):
                # Check if it's a replacement (not a conflict)
                is_replacement = any(word in request2 for word in ["replace", "switch", "instead", "change from"])

                if not is_replacement:
                    conflicts.append({
                        "type": "cloud_provider_conflict",
                        "change_ids": [change1.get("id"), change2.get("id")],
                        "description": f"Conflicting cloud providers: {providers_in_1} vs {providers_in_2}",
                        "change1": change1.get("user_request"),
                        "change2": change2.get("user_request"),
                        "recommendation": "Please clarify which cloud provider to use"
                    })

    # Check for database conflicts (similar logic)
    for i, change1 in enumerate(architecture_changes):
        request1 = change1.get("user_request", "").lower()
        dbs_in_1 = [d for d in databases if d in request1]

        for j, change2 in enumerate(architecture_changes[i+1:], i+1):
            request2 = change2.get("user_request", "").lower()
            dbs_in_2 = [d for d in databases if d in request2]

            if dbs_in_1 and dbs_in_2 and set(dbs_in_1) != set(dbs_in_2):
                is_replacement = any(word in request2 for word in ["replace", "switch", "instead", "change from"])

                if not is_replacement:
                    conflicts.append({
                        "type": "database_conflict",
                        "change_ids": [change1.get("id"), change2.get("id")],
                        "description": f"Conflicting databases: {dbs_in_1} vs {dbs_in_2}",
                        "change1": change1.get("user_request"),
                        "change2": change2.get("user_request"),
                        "recommendation": "Please clarify which database to use"
                    })

    return conflicts


async def get_pending_changes_summary(chat_history_id: str, db: Session) -> dict:
    """
    Get a summary of pending changes for display to user.

    Args:
        chat_history_id: The chat history ID
        db: Database session

    Returns:
        Summary dict with change count, affected sections, and conflicts
    """
    pending = await get_pending_changes(chat_history_id, db)

    if not pending:
        return {
            "has_pending_changes": False,
            "count": 0,
            "changes": [],
            "affected_sections": [],
            "conflicts": []
        }

    # Collect all affected sections
    all_affected = set()
    for change in pending:
        all_affected.update(change.get("affected_sections", []))

    # Detect conflicts
    conflicts = detect_conflicts(pending)

    return {
        "has_pending_changes": True,
        "count": len(pending),
        "changes": pending,
        "affected_sections": list(all_affected),
        "conflicts": conflicts,
        "has_conflicts": len(conflicts) > 0
    }


# ============================================================
# REPORT VERSION MANAGEMENT (Phase 2)
# ============================================================

async def get_all_report_versions(chat_history_id: str, db: Session) -> list:
    """
    Get all report versions for a chat history, ordered by version number descending.

    Args:
        chat_history_id: The chat history ID
        db: Database session

    Returns:
        List of report version records (without full content for efficiency)
    """
    try:
        records = db.query(models.ReportVersions).filter(
            models.ReportVersions.chat_history_id == chat_history_id
        ).order_by(models.ReportVersions.version_number.desc()).all()

        versions = []
        for record in records:
            exec_summary = record.summary_report.get("executive_summary") if record.summary_report else None
            # A short, identifiable name for the version: prefer the changelog of
            # what changed; else the first line of the exec summary; else a number.
            if record.changelog_summary:
                label = record.changelog_summary
            elif record.version_number == 1:
                label = "Initial report"
            elif exec_summary:
                first_line = exec_summary.strip().split("\n")[0]
                label = (first_line[:90] + "…") if len(first_line) > 90 else first_line
            else:
                label = f"Version {record.version_number}"

            versions.append({
                "report_version_id": record.report_version_id,
                "version_number": record.version_number,
                "version": record.version_number,  # Alias for compatibility
                "created_at": record.created_at.isoformat() if record.created_at else None,
                "summary": exec_summary or "No summary available",
                "label": label,
                "is_default": bool(record.is_default),
                "is_latest": record.version_number == records[0].version_number if records else False,
                "is_client_signoff": bool(getattr(record, "is_client_signoff", False)),
                "signoff_at": record.signoff_at.isoformat() if getattr(record, "signoff_at", None) else None,
                # Changelog tracking fields
                "changes_applied": record.changes_applied,
                "changelog_summary": record.changelog_summary,
                "parent_version_id": record.parent_version_id
            })

        return versions

    except SQLAlchemyError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving report versions: {str(e)}"
        )


async def get_report_version_by_number(chat_history_id: str, version_number: int, db: Session) -> dict:
    """
    Get a specific report version by version number.

    Args:
        chat_history_id: The chat history ID
        version_number: The version number to retrieve
        db: Database session

    Returns:
        Full report version record

    Raises:
        HTTPException: If version not found
    """
    try:
        record = db.query(models.ReportVersions).filter(
            models.ReportVersions.chat_history_id == chat_history_id,
            models.ReportVersions.version_number == version_number
        ).first()

        if not record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Report version {version_number} not found for chat_history_id: {chat_history_id}"
            )

        return {
            "report_version_id": record.report_version_id,
            "chat_history_id": record.chat_history_id,
            "user_id": record.user_id,
            "version_number": record.version_number,
            "report_content": record.report_content,
            "summary_report": record.summary_report,
            "report_contract": record.report_contract,  # typed decisions; powers cross-version delta/rank
            "created_at": record.created_at.isoformat() if record.created_at else None,
            "is_client_signoff": bool(getattr(record, "is_client_signoff", False)),
            "signoff_at": record.signoff_at.isoformat() if getattr(record, "signoff_at", None) else None,
            # Changelog tracking fields
            "changes_applied": record.changes_applied,
            "changelog_summary": record.changelog_summary,
            "parent_version_id": record.parent_version_id
        }

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving report version: {str(e)}"
        )


async def create_new_report_version(
    chat_history_id: str,
    user_id: str,
    report_content: str,
    summary_report: dict,
    changes_applied: list,
    db: Session,
    changelog_summary: str = None,
    parent_version_id: str = None,
    report_contract: dict = None,
) -> dict:
    """
    Create a new report version after regeneration.

    Args:
        chat_history_id: The chat history ID
        user_id: The user ID
        report_content: The full regenerated report in markdown
        summary_report: The structured summary of the report
        changes_applied: List of changes that were applied in this version
        db: Database session
        changelog_summary: LLM-generated summary of what changed and implications (optional)
        parent_version_id: ID of the version this was based on (optional)

    Returns:
        Dict with new version details
    """
    try:
        # Get the latest version number
        latest = db.query(models.ReportVersions).filter(
            models.ReportVersions.chat_history_id == chat_history_id
        ).order_by(models.ReportVersions.version_number.desc()).first()

        new_version_number = (latest.version_number + 1) if latest else 1

        # If no parent_version_id provided, use the latest version's ID
        if parent_version_id is None and latest:
            parent_version_id = latest.report_version_id

        # Carry forward the user's Deliverable Builder (A5) curation state when
        # the report's section IDs are unchanged between versions. Polished
        # overrides are always reset because their content is stale by definition.
        carried_config = None
        if latest and latest.deliverable_config:
            try:
                old_ids = {s.id for s in parse_sections(latest.report_content or "")}
                new_ids = {s.id for s in parse_sections(report_content or "")}
                if old_ids and old_ids == new_ids:
                    carried_config = latest.deliverable_config
            except Exception as e:
                # Don't fail the regen path on a parser hiccup; just drop the config.
                logger.warning(f"deliverable_config carry-forward skipped due to parse error: {e}")

        # Set all existing versions to is_default=False before creating new version
        # This ensures only the new version will have is_default=True
        db.query(models.ReportVersions).filter(
            models.ReportVersions.chat_history_id == chat_history_id
        ).update({"is_default": False})

        # Create new version record with changelog tracking
        new_version = models.ReportVersions(
            report_version_id=new_id(),
            chat_history_id=chat_history_id,
            user_id=user_id,
            version_number=new_version_number,
            report_content=report_content,
            summary_report=summary_report,
            pending_changes=[],  # Clear pending changes for new version
            changes_applied=changes_applied,  # Store the changes that created this version
            changelog_summary=changelog_summary,  # Store the changelog summary
            parent_version_id=parent_version_id,  # Track version lineage
            report_contract=report_contract,  # Typed decisions; carried/edited so the new version keeps reality-gap/compare/premortem
            deliverable_config=carried_config,  # A5: carried forward when section IDs match
            deliverable_polished_sections=None,  # A5: always reset; polish content is stale
            deliverable_updated_at=datetime.utcnow() if carried_config else None,
        )

        db.add(new_version)
        db.commit()
        db.refresh(new_version)

        logger.info(f"Created new report version {new_version_number} for chat_history_id: {chat_history_id} with changelog")

        return {
            "status": "success",
            "report_version_id": new_version.report_version_id,
            "version_number": new_version_number,
            "changes_applied": len(changes_applied),
            "changelog_summary": changelog_summary,
            "parent_version_id": parent_version_id,
            "created_at": new_version.created_at.isoformat() if new_version.created_at else None
        }

    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating new report version: {str(e)}"
        )


# ============================================================================
# DELIVERABLE BUILDER (A5) — per-project curation state on report_version
# ============================================================================

def _get_default_report_version(chat_history_id: str, db: Session):
    """Internal: fetch the is_default report_version row for this chat, or None."""
    return (
        db.query(models.ReportVersions)
        .filter(
            models.ReportVersions.chat_history_id == chat_history_id,
            models.ReportVersions.is_default.is_(True),
        )
        .first()
    )


async def get_deliverable_state(chat_history_id: str, db: Session) -> Optional[dict]:
    """Read the Deliverable Builder curation state for a project.

    Returns the source markdown alongside the persisted config + polish so the
    builder UI can render the section list and preview in one round trip.
    Returns None if no report version exists yet for this chat.
    """
    row = _get_default_report_version(chat_history_id, db)
    if not row:
        return None
    return {
        "report_version_id": row.report_version_id,
        "report_content": row.report_content,
        "config": row.deliverable_config,
        "polished_sections": row.deliverable_polished_sections or {},
        "updated_at": row.deliverable_updated_at.isoformat() if row.deliverable_updated_at else None,
    }


async def update_deliverable_config(
    chat_history_id: str,
    config: dict,
    db: Session,
) -> dict:
    """Replace the deliverable_config for the default report_version of this chat.

    The caller is responsible for validating section IDs against the current
    parsed sections (done in the PUT endpoint) — this helper does no validation
    beyond shape coercion.
    """
    row = _get_default_report_version(chat_history_id, db)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No report version found for this chat",
        )
    try:
        row.deliverable_config = config
        row.deliverable_updated_at = datetime.utcnow()
        flag_modified(row, "deliverable_config")
        db.commit()
        db.refresh(row)
        return {
            "status": "success",
            "report_version_id": row.report_version_id,
            "updated_at": row.deliverable_updated_at.isoformat(),
        }
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating deliverable config: {str(e)}",
        )


async def set_polished_section(
    chat_history_id: str,
    section_id: str,
    polished_markdown: str,
    db: Session,
) -> dict:
    """Persist a polished version of one section. Replaces any prior polish for that id."""
    row = _get_default_report_version(chat_history_id, db)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No report version found for this chat",
        )
    try:
        polished = dict(row.deliverable_polished_sections or {})
        polished[section_id] = {
            "markdown": polished_markdown,
            "polished_at": datetime.utcnow().isoformat(),
        }
        row.deliverable_polished_sections = polished
        row.deliverable_updated_at = datetime.utcnow()
        flag_modified(row, "deliverable_polished_sections")
        db.commit()
        return {
            "status": "success",
            "section_id": section_id,
            "polished_at": polished[section_id]["polished_at"],
        }
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error persisting polished section: {str(e)}",
        )


async def revert_polished_section(
    chat_history_id: str,
    section_id: str,
    db: Session,
) -> dict:
    """Remove the polish override for a section so the source/edit markdown is used again."""
    row = _get_default_report_version(chat_history_id, db)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No report version found for this chat",
        )
    try:
        polished = dict(row.deliverable_polished_sections or {})
        polished.pop(section_id, None)
        row.deliverable_polished_sections = polished or None
        row.deliverable_updated_at = datetime.utcnow()
        flag_modified(row, "deliverable_polished_sections")
        db.commit()
        return {"status": "success", "section_id": section_id}
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error reverting polished section: {str(e)}",
        )


async def rollback_to_version(
    chat_history_id: str,
    user_id: str,
    target_version_number: int,
    db: Session
) -> dict:
    """
    Rollback to a previous report version by creating a new version with old content.

    This doesn't delete versions - it creates a new version that copies
    the content from the target version. This preserves full history.

    Args:
        chat_history_id: The chat history ID
        user_id: The user ID
        target_version_number: The version number to rollback to
        db: Database session

    Returns:
        Dict with new version details
    """
    try:
        # Get the target version
        target_version = db.query(models.ReportVersions).filter(
            models.ReportVersions.chat_history_id == chat_history_id,
            models.ReportVersions.version_number == target_version_number
        ).first()

        if not target_version:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Version {target_version_number} not found"
            )

        # Get the latest version number
        latest = db.query(models.ReportVersions).filter(
            models.ReportVersions.chat_history_id == chat_history_id
        ).order_by(models.ReportVersions.version_number.desc()).first()

        if target_version_number == latest.version_number:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Version {target_version_number} is already the latest version"
            )

        new_version_number = latest.version_number + 1

        # Set all existing versions to is_default=False before creating rollback version
        # This ensures only the new rollback version will have is_default=True
        db.query(models.ReportVersions).filter(
            models.ReportVersions.chat_history_id == chat_history_id
        ).update({"is_default": False})

        # Create new version with target's content
        rollback_version = models.ReportVersions(
            report_version_id=new_id(),
            chat_history_id=chat_history_id,
            user_id=user_id,
            version_number=new_version_number,
            report_content=target_version.report_content,
            summary_report=target_version.summary_report,
            pending_changes=[]  # Clear pending changes
        )

        db.add(rollback_version)
        db.commit()
        db.refresh(rollback_version)

        logger.info(f"Rolled back to version {target_version_number} as new version {new_version_number} for chat_history_id: {chat_history_id}")

        return {
            "status": "success",
            "message": f"Rolled back to version {target_version_number}",
            "new_version_number": new_version_number,
            "report_version_id": rollback_version.report_version_id,
            "original_version": target_version_number,
            "report_content": target_version.report_content  # For vector DB update
        }

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error rolling back: {str(e)}"
        )


async def get_report_diff(
    chat_history_id: str,
    version_a: int,
    version_b: int,
    db: Session
) -> dict:
    """
    Get a simple diff between two report versions.

    Args:
        chat_history_id: The chat history ID
        version_a: First version number
        version_b: Second version number
        db: Database session

    Returns:
        Dict with diff information
    """
    try:
        # Get both versions
        ver_a = await get_report_version_by_number(chat_history_id, version_a, db)
        ver_b = await get_report_version_by_number(chat_history_id, version_b, db)

        content_a = ver_a["report_content"]
        content_b = ver_b["report_content"]

        # Basic diff stats
        lines_a = content_a.split('\n')
        lines_b = content_b.split('\n')

        # Count differences
        added_lines = 0
        removed_lines = 0

        # Simple line-based diff
        set_a = set(lines_a)
        set_b = set(lines_b)

        added_lines = len(set_b - set_a)
        removed_lines = len(set_a - set_b)

        return {
            "version_a": version_a,
            "version_b": version_b,
            "stats": {
                "lines_in_a": len(lines_a),
                "lines_in_b": len(lines_b),
                "lines_added": added_lines,
                "lines_removed": removed_lines,
                "chars_in_a": len(content_a),
                "chars_in_b": len(content_b)
            },
            "summary_a": ver_a["summary_report"].get("executive_summary", "") if ver_a["summary_report"] else "",
            "summary_b": ver_b["summary_report"].get("executive_summary", "") if ver_b["summary_report"] else ""
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error computing diff: {str(e)}"
        )


# ============================================================
# REPORT VERSION DEFAULT/RETRIEVAL FUNCTIONS
# ============================================================

async def get_default_report(chat_history_id: str, user_id: str, db: Session) -> dict:
    """
    Get the default (recommended) version of the report.
    Falls back to latest version if no default is explicitly set.

    Args:
        chat_history_id: The chat history ID
        user_id: The user ID (for security validation)
        db: Database session

    Returns:
        Full report version record with report_content

    Raises:
        HTTPException: If no report exists or user validation fails
    """
    try:
        # First try to get explicitly marked default version
        record = db.query(models.ReportVersions).filter(
            models.ReportVersions.chat_history_id == chat_history_id,
            models.ReportVersions.user_id == user_id,
            models.ReportVersions.is_default == True
        ).first()

        # Fall back to latest version if no default set
        if not record:
            record = db.query(models.ReportVersions).filter(
                models.ReportVersions.chat_history_id == chat_history_id,
                models.ReportVersions.user_id == user_id
            ).order_by(models.ReportVersions.version_number.desc()).first()

        if not record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No report found for chat_history_id: {chat_history_id}"
            )

        return {
            "report_version_id": record.report_version_id,
            "chat_history_id": record.chat_history_id,
            "user_id": record.user_id,
            "version_number": record.version_number,
            "report_content": record.report_content,
            "summary_report": record.summary_report,
            "is_default": record.is_default,
            "created_at": record.created_at.isoformat() if record.created_at else None
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving default report: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving default report: {str(e)}"
        )


async def set_default_version(chat_history_id: str, user_id: str, version_number: int, db: Session) -> dict:
    """
    Mark a specific version as the default/recommended version.
    Ensures only one version is marked as default per chat_history_id.

    Args:
        chat_history_id: The chat history ID
        user_id: The user ID (for security validation)
        version_number: The version to mark as default
        db: Database session

    Returns:
        Status dict with updated default version info

    Raises:
        HTTPException: If version not found or user validation fails
    """
    try:
        # First verify the version exists and belongs to this user
        target_version = db.query(models.ReportVersions).filter(
            models.ReportVersions.chat_history_id == chat_history_id,
            models.ReportVersions.user_id == user_id,
            models.ReportVersions.version_number == version_number
        ).first()

        if not target_version:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Version {version_number} not found for this report"
            )

        # Clear existing default for this chat_history_id
        db.query(models.ReportVersions).filter(
            models.ReportVersions.chat_history_id == chat_history_id
        ).update({"is_default": False})

        # Set new default
        target_version.is_default = True
        flag_modified(target_version, "is_default")

        db.commit()
        db.refresh(target_version)

        logger.info(f"Set version {version_number} as default for chat_history_id: {chat_history_id}")

        return {
            "status": "success",
            "version_number": version_number,
            "report_version_id": target_version.report_version_id,
            "message": f"Version {version_number} is now the default version"
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error setting default version: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error setting default version: {str(e)}"
        )


async def set_signoff_version(chat_history_id: str, user_id: str, version_number: int, db: Session) -> dict:
    """Pin one version as the client-signoff baseline (the change-order baseline).

    Exactly one baseline per project — clears any prior pin first. The pinned
    version is what the "since signoff" diff + change-order draft compute against.
    """
    from datetime import datetime, timezone
    try:
        target_version = db.query(models.ReportVersions).filter(
            models.ReportVersions.chat_history_id == chat_history_id,
            models.ReportVersions.user_id == user_id,
            models.ReportVersions.version_number == version_number
        ).first()

        if not target_version:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Version {version_number} not found for this report"
            )

        # One baseline per project — clear any prior pin.
        db.query(models.ReportVersions).filter(
            models.ReportVersions.chat_history_id == chat_history_id
        ).update({"is_client_signoff": False, "signoff_at": None})

        target_version.is_client_signoff = True
        target_version.signoff_at = datetime.now(timezone.utc)
        flag_modified(target_version, "is_client_signoff")

        db.commit()
        db.refresh(target_version)

        logger.info(f"Pinned version {version_number} as client-signoff baseline for chat_history_id: {chat_history_id}")
        return {
            "status": "success",
            "version_number": version_number,
            "report_version_id": target_version.report_version_id,
            "signoff_at": target_version.signoff_at.isoformat(),
            "message": f"Version {version_number} is now the client-signoff baseline",
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error setting signoff version: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error setting signoff version: {str(e)}"
        )


def get_signoff_version_number(chat_history_id: str, db: Session) -> Optional[int]:
    """Return the version_number pinned as the client-signoff baseline, or None."""
    row = db.query(models.ReportVersions).filter(
        models.ReportVersions.chat_history_id == chat_history_id,
        models.ReportVersions.is_client_signoff == True,  # noqa: E712
    ).first()
    return row.version_number if row else None


async def get_report_version_content(chat_history_id: str, version_number: int, db: Session) -> str:
    """
    Get the report content for a specific version number.
    Used for updating vector DB when changing default version.

    Args:
        chat_history_id: The chat history ID
        version_number: The version number to get content for
        db: Database session

    Returns:
        The report content string, or None if not found
    """
    try:
        version = db.query(models.ReportVersions).filter(
            models.ReportVersions.chat_history_id == chat_history_id,
            models.ReportVersions.version_number == version_number
        ).first()

        if version:
            return version.report_content
        return None
    except Exception as e:
        logger.error(f"Error getting report version content: {str(e)}")
        return None


async def get_all_report_versions_enhanced(chat_history_id: str, user_id: str, db: Session) -> list:
    """
    Get all report versions with distinguishing summaries showing what changed in each.

    Args:
        chat_history_id: The chat history ID
        user_id: The user ID (for security)
        db: Database session

    Returns:
        List of version records with change summaries
    """
    try:
        records = db.query(models.ReportVersions).filter(
            models.ReportVersions.chat_history_id == chat_history_id,
            models.ReportVersions.user_id == user_id
        ).order_by(models.ReportVersions.version_number.desc()).all()

        if not records:
            return []

        versions = []

        # Process in ascending order to compare with previous
        for record in reversed(records):
            version_info = {
                "report_version_id": record.report_version_id,
                "version_number": record.version_number,
                "is_default": record.is_default if hasattr(record, 'is_default') else False,
                "is_latest": record.version_number == records[0].version_number,
                "created_at": record.created_at.isoformat() if record.created_at else None,
            }

            # Get executive summary
            exec_summary = ""
            if record.summary_report and isinstance(record.summary_report, dict):
                exec_summary = record.summary_report.get("executive_summary", "")
                if isinstance(exec_summary, str) and len(exec_summary) > 150:
                    exec_summary = exec_summary[:150] + "..."

            version_info["executive_summary"] = exec_summary

            # Generate change description
            if record.version_number == 1:
                version_info["change_description"] = "Initial report generation"
            else:
                # Extract change hints from summary_report if available
                notes = record.summary_report.get("notes_for_router_llm", {}) if record.summary_report else {}
                if notes:
                    version_info["change_description"] = "Updated based on modifications"
                else:
                    version_info["change_description"] = "Report regeneration"

            versions.append(version_info)

        # Return in descending order (latest first)
        return list(reversed(versions))
    except Exception as e:
        logger.error(f"Error retrieving report versions: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving report versions: {str(e)}"
        )


# ============================================================
# PRE-SALES WORKFLOW DATABASE FUNCTIONS
# ============================================================

async def save_presales_analysis(presales_data: dict, db: Session) -> dict:
    """
    Save pre-sales analysis results to database.

    Args:
        presales_data: Dict containing:
            - document_id: The document ID
            - user_id: The user ID
            - scanned_requirements: Output from scanner agent (dict)
            - blind_spots: Output from blind spot detector (dict)
            - p1_blockers: P1 blockers with questions (list)
            - technology_risks: List of tech risks (list)
            - kickstart_questions: Critical questions for client (list)
            - presales_brief: Final markdown brief (str)
            - status: Analysis status (str)
            - model_used: Model name used (str)
            - processing_time_seconds: Time taken (int)
        db: Database session

    Returns:
        Dict with presales_id and status

    Raises:
        HTTPException: If save fails
    """
    try:
        # Allow caller to pre-generate the presales_id so it can be passed to
        # the LLM recorder *before* the scan runs (lets us tag every initial-scan
        # llm_call_log row with the project-level identifier). Falls through to
        # the model default uuid if not supplied.
        kwargs = {}
        if presales_data.get("presales_id"):
            kwargs["presales_id"] = presales_data["presales_id"]
        presales = models.PresalesAnalysis(
            **kwargs,
            document_id=presales_data["document_id"],
            user_id=presales_data["user_id"],
            extracted_requirements=presales_data.get("scanned_requirements"),
            blind_spots=presales_data.get("blind_spots"),
            p1_blockers=presales_data.get("p1_blockers"),
            technology_risks=presales_data.get("technology_risks"),
            kickstart_questions=presales_data.get("kickstart_questions"),
            presales_brief=presales_data.get("presales_brief"),
            status=presales_data.get("status", "completed"),
            model_used=presales_data.get("model_used"),
            processing_time_seconds=presales_data.get("processing_time_seconds")
        )

        db.add(presales)
        db.commit()
        db.refresh(presales)

        logger.info(f"Saved presales analysis: {presales.presales_id} for document: {presales.document_id}")

        return {
            "presales_id": presales.presales_id,
            "document_id": presales.document_id,
            "status": presales.status
        }

    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error saving presales analysis: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error saving presales analysis: {str(e)}"
        )


async def save_technology_risks(
    risks: list,
    presales_id: str,
    document_id: str,
    user_id: str,
    model_used: str,
    db: Session
) -> dict:
    """
    Save raised technology risks for future analysis.

    This passively captures risks identified by the LLM for:
    - Analyzing which risks are raised most often
    - Understanding which risks were actually relevant
    - Improving prompts based on feedback

    Args:
        risks: List of risk dicts from blind spot detector
        presales_id: The presales analysis ID
        document_id: The document ID
        user_id: The user ID
        model_used: Model name that raised these risks
        db: Database session

    Returns:
        Dict with count of saved risks
    """
    if not risks:
        return {"saved_count": 0}

    try:
        saved_count = 0
        for risk in risks:
            risk_record = models.RaisedTechnologyRisk(
                presales_id=presales_id,
                document_id=document_id,
                user_id=user_id,
                technologies=risk.get("technologies", []),
                risk_title=risk.get("risk_title", "Unknown Risk"),
                risk_description=risk.get("description"),
                severity=risk.get("severity"),
                category=risk.get("category"),
                model_used=model_used
            )
            db.add(risk_record)
            saved_count += 1

        db.commit()
        logger.info(f"Saved {saved_count} technology risks for presales: {presales_id}")

        return {"saved_count": saved_count}

    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error saving technology risks: {str(e)}")
        # Don't raise - this is passive capture, shouldn't block main flow
        return {"saved_count": 0, "error": str(e)}


async def get_presales_analysis(document_id: str, user_id: str, db: Session) -> dict:
    """
    Get pre-sales analysis for a document.

    Args:
        document_id: The document ID
        user_id: The user ID (for security filtering)
        db: Database session

    Returns:
        Dict with presales analysis data, or None if not found
    """
    try:
        presales = db.query(models.PresalesAnalysis).filter(
            models.PresalesAnalysis.document_id == document_id,
            models.PresalesAnalysis.user_id == user_id
        ).order_by(models.PresalesAnalysis.created_at.desc()).first()

        if not presales:
            return None

        return {
            "presales_id": presales.presales_id,
            "document_id": presales.document_id,
            "user_id": presales.user_id,
            "extracted_requirements": presales.extracted_requirements,
            "blind_spots": presales.blind_spots,
            "p1_blockers": presales.p1_blockers,
            "technology_risks": presales.technology_risks,
            "kickstart_questions": presales.kickstart_questions,
            "presales_brief": presales.presales_brief,
            "status": presales.status,
            "model_used": presales.model_used,
            "processing_time_seconds": presales.processing_time_seconds,
            "created_at": presales.created_at.isoformat() if presales.created_at else None,
            # Client-questionnaire submission record (proof of who/when).
            "client_submitted_at": presales.client_submitted_at.isoformat() if presales.client_submitted_at else None,
            "client_respondent": presales.client_respondent if isinstance(presales.client_respondent, dict) else None,
        }

    except SQLAlchemyError as e:
        logger.error(f"Error getting presales analysis: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving presales analysis: {str(e)}"
        )


async def get_presales_by_chat_history(chat_history_id: str, db: Session) -> dict:
    """
    Get pre-sales analysis for a chat history session.
    Resolves chat_history_id to document_id and retrieves presales analysis.

    Args:
        chat_history_id: The chat history ID
        db: Database session

    Returns:
        Dict with presales analysis data, or None if not found
    """
    try:
        # First get the chat history to get document_id and user_id
        chat_history = db.query(models.ChatHistory).filter(
            models.ChatHistory.chat_history_id == chat_history_id
        ).first()

        if not chat_history:
            return None

        # Now get presales analysis using document_id and user_id
        presales = db.query(models.PresalesAnalysis).filter(
            models.PresalesAnalysis.document_id == chat_history.document_id,
            models.PresalesAnalysis.user_id == chat_history.user_id
        ).order_by(models.PresalesAnalysis.created_at.desc()).first()

        if not presales:
            return None

        return {
            "presales_id": presales.presales_id,
            "document_id": presales.document_id,
            "user_id": presales.user_id,
            "extracted_requirements": presales.extracted_requirements,
            "blind_spots": presales.blind_spots,
            "p1_blockers": presales.p1_blockers,
            "technology_risks": presales.technology_risks,
            "kickstart_questions": presales.kickstart_questions,
            "red_flags": getattr(presales, 'red_flags', None),
            "critical_unknowns": getattr(presales, 'critical_unknowns', None),
            "presales_brief": presales.presales_brief,
            "status": presales.status,
            "model_used": presales.model_used,
            "processing_time_seconds": presales.processing_time_seconds,
            "created_at": presales.created_at.isoformat() if presales.created_at else None
        }

    except SQLAlchemyError as e:
        logger.error(f"Error getting presales analysis by chat history: {str(e)}")
        return None


async def get_presales_by_id(presales_id: str, user_id: str, db: Session) -> dict:
    """
    Get pre-sales analysis by its ID.

    Args:
        presales_id: The presales analysis ID
        user_id: The user ID (for security filtering)
        db: Database session

    Returns:
        Dict with presales analysis data

    Raises:
        HTTPException: If not found
    """
    try:
        presales = db.query(models.PresalesAnalysis).filter(
            models.PresalesAnalysis.presales_id == presales_id,
            models.PresalesAnalysis.user_id == user_id
        ).first()

        if not presales:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Presales analysis not found: {presales_id}"
            )

        return {
            "presales_id": presales.presales_id,
            "document_id": presales.document_id,
            "user_id": presales.user_id,
            "extracted_requirements": presales.extracted_requirements,
            "blind_spots": presales.blind_spots,
            "p1_blockers": presales.p1_blockers,
            "technology_risks": presales.technology_risks,
            "kickstart_questions": presales.kickstart_questions,
            "presales_brief": presales.presales_brief,
            "status": presales.status,
            "model_used": presales.model_used,
            "processing_time_seconds": presales.processing_time_seconds,
            "created_at": presales.created_at.isoformat() if presales.created_at else None
        }

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Error getting presales analysis by ID: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving presales analysis: {str(e)}"
        )


async def create_analysis_link(
    document_id: str,
    user_id: str,
    presales_id: str,
    db: Session,
    chat_history_id: str = None
) -> dict:
    """
    Create a link between document, presales analysis, and chat history.

    This allows tracking the journey from pre-sales scan to full report,
    and enables presales to appear in conversation history.

    Args:
        document_id: The document ID
        user_id: The user ID
        presales_id: The presales analysis ID
        db: Database session
        chat_history_id: Optional chat history ID to link immediately

    Returns:
        Dict with link_id and chat_history_id
    """
    try:
        link = models.AnalysisLink(
            document_id=document_id,
            user_id=user_id,
            presales_id=presales_id,
            chat_history_id=chat_history_id
        )

        db.add(link)
        db.commit()
        db.refresh(link)

        logger.info(f"Created analysis link: {link.link_id} for document: {document_id}, chat_history: {chat_history_id}")

        return {"link_id": link.link_id, "chat_history_id": chat_history_id}

    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error creating analysis link: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating analysis link: {str(e)}"
        )


async def get_analysis_link(document_id: str, user_id: str, db: Session) -> dict:
    """
    Get analysis link for a document.

    Args:
        document_id: The document ID
        user_id: The user ID (for security filtering)
        db: Database session

    Returns:
        Dict with link data, or None if not found
    """
    try:
        link = db.query(models.AnalysisLink).filter(
            models.AnalysisLink.document_id == document_id,
            models.AnalysisLink.user_id == user_id
        ).first()

        if not link:
            return None

        return {
            "link_id": link.link_id,
            "document_id": link.document_id,
            "user_id": link.user_id,
            "presales_id": link.presales_id,
            "chat_history_id": link.chat_history_id,
            "user_answers": link.user_answers,
            "full_report_requested": link.full_report_requested,
            "full_report_generated": link.full_report_generated,
            "created_at": link.created_at.isoformat() if link.created_at else None
        }

    except SQLAlchemyError as e:
        logger.error(f"Error getting analysis link: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving analysis link: {str(e)}"
        )


async def get_analysis_link_by_presales_id(presales_id: str, user_id: str, db: Session) -> dict:
    """
    Get analysis link by presales_id.

    Args:
        presales_id: The presales analysis ID
        user_id: The user ID (for security filtering)
        db: Database session

    Returns:
        Dict with link data, or None if not found
    """
    try:
        link = db.query(models.AnalysisLink).filter(
            models.AnalysisLink.presales_id == presales_id,
            models.AnalysisLink.user_id == user_id
        ).first()

        if not link:
            return None

        return {
            "link_id": link.link_id,
            "document_id": link.document_id,
            "user_id": link.user_id,
            "presales_id": link.presales_id,
            "chat_history_id": link.chat_history_id,
            "user_answers": link.user_answers,
            "full_report_requested": link.full_report_requested,
            "full_report_generated": link.full_report_generated,
            "created_at": link.created_at.isoformat() if link.created_at else None
        }

    except SQLAlchemyError as e:
        logger.error(f"Error getting analysis link by presales_id: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving analysis link: {str(e)}"
        )


def get_presales_id_for_chat(chat_history_id: str, db: Session) -> Optional[str]:
    """
    Resolve the presales_id linked to a chat_history_id, or None.

    Used by telemetry (utils/llm_metrics.py) so chat-with-doc and regenerate-report
    LLM calls can be rolled up against the project (presales_id) the chat belongs
    to. Returns None for legacy chats that predate AnalysisLink — telemetry must
    not fail because of missing linkage.
    """
    if not chat_history_id:
        return None
    try:
        link = db.query(models.AnalysisLink).filter(
            models.AnalysisLink.chat_history_id == chat_history_id
        ).first()
        return link.presales_id if link else None
    except Exception as e:
        logger.warning(f"get_presales_id_for_chat failed for {chat_history_id}: {e}")
        return None


def get_analysis_mode(chat_history_id: str, db: Session) -> dict:
    """
    Get analysis mode for a chat history.

    Determines if a chat is in 'presales' or 'full' mode based on the AnalysisLink.
    - If full_report_generated is True → 'full' mode
    - If presales_id exists but full_report_generated is False → 'presales' mode
    - If no link exists → 'full' mode (default)

    Args:
        chat_history_id: The chat history ID
        db: Database session

    Returns:
        Dict with analysis_mode ('full' or 'presales') and presales_id
    """
    try:
        link = db.query(models.AnalysisLink).filter(
            models.AnalysisLink.chat_history_id == chat_history_id
        ).first()

        if not link:
            # No link found - could be a direct full report or old chat
            # Default to 'full' mode
            return {"analysis_mode": "full", "presales_id": None}

        # Determine mode based on full_report_generated flag
        if link.full_report_generated:
            return {
                "analysis_mode": "full",
                "presales_id": link.presales_id
            }
        else:
            return {
                "analysis_mode": "presales",
                "presales_id": link.presales_id
            }

    except SQLAlchemyError as e:
        logger.error(f"Error getting analysis mode for chat_history_id {chat_history_id}: {str(e)}")
        # Return default on error
        return {"analysis_mode": "full", "presales_id": None}


async def update_analysis_link_with_full_report(
    presales_id: str,
    chat_history_id: str,
    db: Session
) -> dict:
    """
    Update analysis link when full report is generated.

    Args:
        presales_id: The presales analysis ID
        chat_history_id: The chat history ID for the full report
        db: Database session

    Returns:
        Dict with updated link data
    """
    try:
        link = db.query(models.AnalysisLink).filter(
            models.AnalysisLink.presales_id == presales_id
        ).first()

        if not link:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No analysis link found for presales: {presales_id}"
            )

        link.chat_history_id = chat_history_id
        link.full_report_requested = True
        link.full_report_generated = True

        db.commit()
        db.refresh(link)

        logger.info(f"Updated analysis link with full report for presales: {presales_id}")

        return {
            "link_id": link.link_id,
            "full_report_generated": True,
            "chat_history_id": chat_history_id
        }

    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error updating analysis link: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating analysis link: {str(e)}"
        )


async def save_user_answers(
    presales_id: str,
    user_answers: dict,
    db: Session
) -> dict:
    """
    Save user answers to kickstart questions before full report generation.

    Args:
        presales_id: The presales analysis ID
        user_answers: Dict of question -> answer mappings
        db: Database session

    Returns:
        Dict with status
    """
    try:
        link = db.query(models.AnalysisLink).filter(
            models.AnalysisLink.presales_id == presales_id
        ).first()

        if not link:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No analysis link found for presales: {presales_id}"
            )

        # Merge with existing answers if any
        existing_answers = link.user_answers or {}
        existing_answers.update(user_answers)
        link.user_answers = existing_answers

        flag_modified(link, "user_answers")

        db.commit()
        db.refresh(link)

        logger.info(f"Saved user answers for presales: {presales_id}")

        return {
            "status": "success",
            "answers_count": len(link.user_answers)
        }

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error saving user answers: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error saving user answers: {str(e)}"
        )


async def mark_risk_relevance(
    risk_id: str,
    user_id: str,
    was_relevant: bool,
    user_feedback: str,
    db: Session
) -> dict:
    """
    Mark whether a raised technology risk was actually relevant.

    This is used for future analysis and prompt improvement.

    Args:
        risk_id: The risk ID
        user_id: The user ID (for security filtering)
        was_relevant: True if risk was real, False if not applicable
        user_feedback: Optional feedback from SA/user
        db: Database session

    Returns:
        Dict with status
    """
    try:
        risk = db.query(models.RaisedTechnologyRisk).filter(
            models.RaisedTechnologyRisk.risk_id == risk_id,
            models.RaisedTechnologyRisk.user_id == user_id
        ).first()

        if not risk:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Risk not found: {risk_id}"
            )

        risk.was_relevant = was_relevant
        risk.user_feedback = user_feedback

        db.commit()
        db.refresh(risk)

        logger.info(f"Marked risk {risk_id} relevance: {was_relevant}")

        return {
            "status": "success",
            "risk_id": risk_id,
            "was_relevant": was_relevant
        }

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error marking risk relevance: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error marking risk relevance: {str(e)}"
        )


async def get_user_presales_history(user_id: str, db: Session, limit: int = 20) -> list:
    """
    Get pre-sales analysis history for a user.

    Args:
        user_id: The user ID
        db: Database session
        limit: Maximum number of results

    Returns:
        List of presales analysis summaries
    """
    try:
        analyses = db.query(models.PresalesAnalysis).filter(
            models.PresalesAnalysis.user_id == user_id
        ).order_by(models.PresalesAnalysis.created_at.desc()).limit(limit).all()

        result = []
        for analysis in analyses:
            # Extract project title from scanned requirements
            title = "Untitled Analysis"
            if analysis.extracted_requirements:
                summary = analysis.extracted_requirements.get("project_summary", "")
                if summary:
                    title = summary[:100] + "..." if len(summary) > 100 else summary

            result.append({
                "presales_id": analysis.presales_id,
                "document_id": analysis.document_id,
                "title": title,
                "status": analysis.status,
                "processing_time_seconds": analysis.processing_time_seconds,
                "created_at": analysis.created_at.isoformat() if analysis.created_at else None
            })

        return result

    except SQLAlchemyError as e:
        logger.error(f"Error getting user presales history: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving presales history: {str(e)}"
        )


# =============================================================================
# PRESALES QUESTION MANAGEMENT
# =============================================================================

async def create_presales_questions(
    presales_id: str,
    user_id: str,
    p1_blockers: list,
    kickstart_questions: list,
    db: Session
) -> dict:
    """
    Create question records from presales analysis results.

    Args:
        presales_id: The presales analysis ID
        user_id: The user ID
        p1_blockers: List of P1 blocker dicts from blind spot detector
        kickstart_questions: List of kickstart question dicts
        db: Database session

    Returns:
        Dict with counts of created questions
    """
    try:
        questions_created = []
        display_order = 0

        # Create P1 blocker questions
        for idx, p1 in enumerate(p1_blockers or []):
            question = models.PresalesQuestion(
                presales_id=presales_id,
                user_id=user_id,
                question_type=models.QuestionType.P1_BLOCKER,
                question_number=f"P1-{idx + 1}",
                display_order=display_order,
                area_or_category=p1.get("area", ""),
                title=p1.get("blocker", ""),
                description=p1.get("why_it_matters", ""),
                question_text=p1.get("question", ""),
                status=models.QuestionStatus.PENDING
            )
            db.add(question)
            questions_created.append(question)
            display_order += 1

        # Create kickstart questions
        for idx, ks in enumerate(kickstart_questions or []):
            question = models.PresalesQuestion(
                presales_id=presales_id,
                user_id=user_id,
                question_type=models.QuestionType.KICKSTART,
                question_number=f"Q{idx + 1}",
                display_order=display_order,
                area_or_category=ks.get("category", ""),
                title=ks.get("question", ""),
                description=ks.get("why_critical", ""),
                impact_description=ks.get("impact_if_unknown", ""),
                question_text=ks.get("question", ""),
                status=models.QuestionStatus.PENDING
            )
            db.add(question)
            questions_created.append(question)
            display_order += 1

        db.commit()

        logger.info(f"Created {len(questions_created)} questions for presales: {presales_id}")

        return {
            "p1_count": len(p1_blockers or []),
            "kickstart_count": len(kickstart_questions or []),
            "total_count": len(questions_created)
        }

    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error creating presales questions: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating questions: {str(e)}"
        )


def _normalize_question_text(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace — for fuzzy comparison."""
    import re as _re
    return _re.sub(r"\s+", " ", _re.sub(r"[^\w\s]", " ", (text or "").lower())).strip()


def _is_duplicate_question(text: str, existing_norms: list) -> bool:
    """Fuzzy duplicate check: the analyzer re-asks the same gap in new words on
    every re-run, so exact-match dedupe is not enough. SequenceMatcher on
    normalized text catches rewordings; 0.72 is deliberately loose — a wrongly
    suppressed follow-up costs nothing (the gap becomes an assumption), while a
    duplicate question burns user trust."""
    from difflib import SequenceMatcher
    norm = _normalize_question_text(text)
    if not norm:
        return True
    for other in existing_norms:
        if not other:
            continue
        if norm == other or SequenceMatcher(None, norm, other).ratio() >= 0.72:
            return True
    return False


# The analyzer runs on every visit to the Analysis step; without a ceiling the
# follow-up list grows 2 per visit forever. Past this many, gaps become
# assumptions instead of more questions.
MAX_FOLLOWUPS_PER_PRESALES = 4


async def create_followup_questions(
    presales_id: str,
    user_id: str,
    follow_ups: list,
    db: Session,
) -> list:
    """Persist analyzer-generated follow-up questions as real PresalesQuestion rows.

    The answer analyzer returns up to 2 `follow_up_questions` per analysis; until
    now they were returned to the API response and discarded — the user never got
    to answer them. Numbered F1, F2, ... (continuing across analyses), appended
    after existing questions, FUZZY-deduped against every question already on the
    analysis (any phrasing) and hard-capped at MAX_FOLLOWUPS_PER_PRESALES total,
    so analysis re-runs can never pile up rewordings of the same gap. Returns the
    created rows as dicts (empty list when everything was a duplicate)."""
    try:
        existing = db.query(models.PresalesQuestion).filter(
            models.PresalesQuestion.presales_id == presales_id,
            models.PresalesQuestion.user_id == user_id,
        ).all()
        existing_norms = [_normalize_question_text(q.question_text or "") for q in existing]
        existing_followups = sum(1 for q in existing if q.question_type == models.QuestionType.FOLLOW_UP)
        next_f_number = existing_followups + 1
        next_order = max((q.display_order or 0 for q in existing), default=-1) + 1

        created = []
        for fu in follow_ups or []:
            if existing_followups + len(created) >= MAX_FOLLOWUPS_PER_PRESALES:
                logger.info(
                    f"Follow-up cap ({MAX_FOLLOWUPS_PER_PRESALES}) reached for presales {presales_id}; "
                    "remaining suggestions dropped — gaps stay covered by assumptions"
                )
                break
            if not isinstance(fu, dict):
                continue
            text = (fu.get("question_text") or "").strip()
            if not text or _is_duplicate_question(text, existing_norms):
                if text:
                    logger.info(f"Skipped duplicate follow-up for presales {presales_id}: {text[:80]!r}")
                continue
            question = models.PresalesQuestion(
                presales_id=presales_id,
                user_id=user_id,
                question_type=models.QuestionType.FOLLOW_UP,
                question_number=f"F{next_f_number}",
                display_order=next_order,
                area_or_category="follow-up",
                title=text,
                description=fu.get("reason", ""),
                impact_description=(
                    f"Triggered by your answer to {fu['based_on']}" if fu.get("based_on") else ""
                ),
                question_text=text,
                status=models.QuestionStatus.PENDING,
            )
            db.add(question)
            created.append(question)
            existing_norms.append(_normalize_question_text(text))
            next_f_number += 1
            next_order += 1

        if created:
            db.commit()
            logger.info(f"Created {len(created)} follow-up question(s) for presales: {presales_id}")
        return [
            {
                "question_id": q.question_id,
                "question_number": q.question_number,
                "question_text": q.question_text,
                "question_type": q.question_type,
            }
            for q in created
        ]

    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error creating follow-up questions: {str(e)}")
        # Follow-ups are enrichment — never fail the analyze call over them.
        return []


async def get_presales_questions(
    presales_id: str,
    user_id: str,
    db: Session,
    include_invalid: bool = True
) -> list:
    """
    Get all questions for a presales analysis.

    Args:
        presales_id: The presales analysis ID
        user_id: The user ID (for security)
        db: Database session
        include_invalid: Whether to include invalidated questions

    Returns:
        List of question dicts
    """
    try:
        query = db.query(models.PresalesQuestion).filter(
            models.PresalesQuestion.presales_id == presales_id,
            models.PresalesQuestion.user_id == user_id
        )

        if not include_invalid:
            query = query.filter(
                models.PresalesQuestion.status != models.QuestionStatus.INVALID
            )

        questions = query.order_by(models.PresalesQuestion.display_order).all()

        return [
            {
                "question_id": q.question_id,
                "presales_id": q.presales_id,
                "question_type": q.question_type,
                "question_number": q.question_number,
                "display_order": q.display_order,
                "area_or_category": q.area_or_category,
                "title": q.title,
                "description": q.description,
                "impact_description": q.impact_description,
                "question_text": q.question_text,
                "answer": q.answer,
                "answer_quality": q.answer_quality,
                "answer_feedback": q.answer_feedback,
                "answered_at": q.answered_at.isoformat() if q.answered_at else None,
                "answered_by": q.answered_by,
                "status": q.status,
                "invalidated_reason": q.invalidated_reason,
                "invalidated_at": q.invalidated_at.isoformat() if q.invalidated_at else None,
                "created_at": q.created_at.isoformat() if q.created_at else None
            }
            for q in questions
        ]

    except SQLAlchemyError as e:
        logger.error(f"Error getting presales questions: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving questions: {str(e)}"
        )


# ---------------------------------------------------------------------------
# Client questionnaire share link (WS-3) — a public, no-login surface for the
# client to answer the firm's questions. The opaque token is the only secret.
# ---------------------------------------------------------------------------

def create_or_get_share_token(presales_id: str, user_id: str, db: Session) -> dict:
    """Ensure a share token exists for this presales analysis (owner-scoped); return it."""
    import uuid
    row = db.query(models.PresalesAnalysis).filter(
        models.PresalesAnalysis.presales_id == presales_id,
        models.PresalesAnalysis.user_id == user_id,
    ).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Presales analysis not found")
    if not row.client_share_token:
        row.client_share_token = uuid.uuid4().hex
        db.commit()
    return {"token": row.client_share_token, "presales_id": presales_id}


def revoke_share_token(presales_id: str, user_id: str, db: Session) -> dict:
    """Null the share token (owner-scoped) — the public link stops working immediately."""
    row = db.query(models.PresalesAnalysis).filter(
        models.PresalesAnalysis.presales_id == presales_id,
        models.PresalesAnalysis.user_id == user_id,
    ).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Presales analysis not found")
    row.client_share_token = None
    db.commit()
    return {"status": "revoked", "presales_id": presales_id}


def get_presales_by_share_token(token: str, db: Session):
    """Return the PresalesAnalysis ORM row for a share token, or None. No user scope —
    the token IS the authorization."""
    if not token:
        return None
    return db.query(models.PresalesAnalysis).filter(
        models.PresalesAnalysis.client_share_token == token
    ).first()


async def submit_client_answers(presales_id: str, answers: dict, db: Session) -> dict:
    """Write client-submitted answers (public, no user scope — the token authorized
    the caller). Marks each as answered_by='client' + status=NEEDS_REVIEW so the BA
    reviews before they feed the report. Mirrors update_question_answers minus the
    owner check; never invalidates or touches firm-only fields.

    The client may edit any answer (incl. firm pre-fills); the firm's control is the
    revoke link, not per-field locks. Skips unchanged answers (autosave re-sends the
    whole form)."""
    from datetime import datetime
    try:
        updated = 0
        for question_id, answer in (answers or {}).items():
            ans = (answer or "").strip()
            if not ans:
                continue
            if len(ans) > 4000:
                ans = ans[:4000]
            q = db.query(models.PresalesQuestion).filter(
                models.PresalesQuestion.question_id == question_id,
                models.PresalesQuestion.presales_id == presales_id,
            ).first()
            if not q:
                continue
            # The client may edit ANY answer — including ones the firm pre-filled as a
            # starting point. The firm's control against unwanted edits is revoking the
            # link (manual + auto-on-finalize), not per-field locks. A client edit flips
            # the question to client/needs_review so the firm reviews it.
            # Autosave re-sends the whole form; skip unchanged answers so we don't spam
            # history rows or redundant writes on every keystroke pause.
            if (q.answer or "") == ans:
                continue
            db.add(models.PresalesAnswerHistory(
                question_id=question_id, presales_id=presales_id,
                previous_answer=q.answer, new_answer=ans,
                change_type="updated" if q.answer else "created", changed_by="client",
            ))
            q.answer = ans
            q.answered_at = datetime.utcnow()
            q.answered_by = "client"
            q.status = models.QuestionStatus.NEEDS_REVIEW
            updated += 1
        db.commit()
        logger.info(f"Client submitted {updated} answer(s) for presales {presales_id}")
        return {"updated_count": updated}
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error submitting client answers: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error submitting answers: {str(e)}")


def mark_link_shared(presales_id: str, user_id: str, db: Session) -> None:
    """Stamp client_link_shared_at (owner-scoped) — set when the firm emails the link
    OR marks it manually shared. Drives the dashboard 'sent' status. Idempotent-ish:
    only sets it the first time (preserves the original share moment)."""
    from datetime import datetime, timezone
    row = db.query(models.PresalesAnalysis).filter(
        models.PresalesAnalysis.presales_id == presales_id,
        models.PresalesAnalysis.user_id == user_id,
    ).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Presales analysis not found")
    if not row.client_link_shared_at:
        row.client_link_shared_at = datetime.now(timezone.utc)
        db.commit()


def set_project_custom_title(chat_history_id: str, user_id: str, custom_title: Optional[str], db: Session) -> dict:
    """Set/clear the firm's display name for a project card (owner-scoped). The LLM
    `title` is left intact as the searchable fallback."""
    row = db.query(models.ChatHistory).filter(
        models.ChatHistory.chat_history_id == chat_history_id,
        models.ChatHistory.user_id == user_id,
    ).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    name = (custom_title or "").strip()[:200]
    row.custom_title = name or None
    db.commit()
    return {"chat_history_id": chat_history_id, "custom_title": row.custom_title, "title": row.title}


def set_client_email(presales_id: str, user_id: str, email: str, db: Session) -> None:
    """Store the client's email on the presales row (owner-scoped) for reminders."""
    row = db.query(models.PresalesAnalysis).filter(
        models.PresalesAnalysis.presales_id == presales_id,
        models.PresalesAnalysis.user_id == user_id,
    ).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Presales analysis not found")
    row.client_email = (email or "").strip()[:320] or None
    db.commit()


def get_firm_email_template_fields(firm_id: Optional[str], template_key: str, db: Session) -> dict:
    """Return the per-firm override fields for a client-email template key, or {}.
    Only the text fields are stored; the GroundedIQ shell is applied at render."""
    if not firm_id:
        return {}
    row = db.query(models.Firm).filter(models.Firm.firm_id == firm_id).first()
    tmpls = (row.email_templates if row and isinstance(row.email_templates, dict) else None) or {}
    fields = tmpls.get(template_key)
    return fields if isinstance(fields, dict) else {}


def set_firm_email_template(firm_id: str, template_key: str, fields: dict, db: Session) -> dict:
    """Upsert (staff-only) the override fields for one firm + template key. Only known
    text fields are stored; everything else is ignored (no raw HTML, no brand override)."""
    from sqlalchemy.orm.attributes import flag_modified
    ALLOWED = {"subject", "heading", "intro", "button_label", "signoff"}
    row = db.query(models.Firm).filter(models.Firm.firm_id == firm_id).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Firm not found")
    tmpls = dict(row.email_templates) if isinstance(row.email_templates, dict) else {}
    clean = {k: (str(v)[:2000] if v is not None else "") for k, v in (fields or {}).items() if k in ALLOWED}
    tmpls[template_key] = clean
    row.email_templates = tmpls
    flag_modified(row, "email_templates")
    db.commit()
    return clean


def list_firms(search: Optional[str], db: Session, limit: int = 50) -> list:
    """Searchable firm list for the admin console dropdown (id + name)."""
    q = db.query(models.Firm.firm_id, models.Firm.name)
    if search and search.strip():
        q = q.filter(models.Firm.name.ilike(f"%{search.strip()}%"))
    rows = q.order_by(models.Firm.name).limit(max(1, min(limit, 200))).all()
    return [{"firm_id": fid, "name": name} for fid, name in rows]


def bump_client_check_count(presales_id: str, db: Session) -> int:
    """Increment and return the durable lifetime readiness-check counter for a
    presales link. Called when a public 'Check readiness' decides to run the LLM,
    so even failed/abusive attempts count against the per-token ceiling."""
    row = db.query(models.PresalesAnalysis).filter(
        models.PresalesAnalysis.presales_id == presales_id
    ).first()
    if not row:
        return 0
    row.client_check_count = (row.client_check_count or 0) + 1
    db.commit()
    return row.client_check_count


def mark_client_submitted(token: str, db: Session, respondent: Optional[dict] = None):
    """Stamp client_submitted_at (+ who completed it) on the presales row for a share
    token (public). Returns the row, or None if the token is invalid/revoked."""
    from datetime import datetime, timezone
    from sqlalchemy.orm.attributes import flag_modified
    row = db.query(models.PresalesAnalysis).filter(
        models.PresalesAnalysis.client_share_token == token
    ).first()
    if not row:
        return None
    row.client_submitted_at = datetime.now(timezone.utc)
    if isinstance(respondent, dict) and (respondent.get("name") or respondent.get("email")):
        row.client_respondent = {
            "name": (respondent.get("name") or "").strip()[:160],
            "designation": (respondent.get("designation") or "").strip()[:160],
            "email": (respondent.get("email") or "").strip()[:320],
        }
        flag_modified(row, "client_respondent")
    db.commit()
    return row


def revoke_share_token_for_presales(presales_id: str, db: Session) -> None:
    """Null the share token for a presales WITHOUT a user scope — used by the
    pipeline kickoff to auto-close the client link when the report is generated."""
    row = db.query(models.PresalesAnalysis).filter(
        models.PresalesAnalysis.presales_id == presales_id
    ).first()
    if row and row.client_share_token:
        row.client_share_token = None
        db.commit()


async def build_structured_crd(
    presales_id: str, user_id: str, presales: dict, presales_brief_text: str, db: Session,
) -> str:
    """Build the structured CRD block the contract planner consumes (settled Q&A +
    accepted assumptions + open questions + approved brief, as typed JSON).

    Lives here (not in routers/services) so BOTH the REST regenerate endpoint and
    the chat/stream regenerate paths can build the identical CRD without an import
    cycle. Never raises: any failure degrades to the brief alone."""
    try:
        questions = await get_presales_questions(presales_id, user_id, db, include_invalid=False)
    except Exception as e:  # noqa: BLE001 — CRD enrichment must not block the run
        logger.warning(f"build_structured_crd: question fetch failed for {presales_id}: {e}")
        questions = []

    confirmed = [
        {"question": q["question_text"], "answer": q["answer"],
         "source": q["question_number"], "category": q.get("area_or_category") or ""}
        for q in questions if q.get("answer") and q.get("status") == "answered"
    ]
    open_questions = [
        {"question": q["question_text"], "source": q["question_number"],
         "severity_hint": "blocker" if q.get("question_type") == "p1_blocker" else "high"}
        for q in questions if not q.get("answer")
    ]
    assumptions = [
        {"assumption": a.get("assumption", ""), "risk_level": a.get("risk_level", ""),
         "basis": a.get("basis", ""), "impact_if_wrong": a.get("impact_if_wrong", ""),
         "for_question_id": a.get("for_question_id", "")}
        for a in (presales.get("assumptions_list") or [])
        if isinstance(a, dict) and a.get("assumption")
    ]
    parts = [
        "## CONFIRMED Q&A (settled facts — copy each into client_qa with its `source` id)",
        json.dumps(confirmed, indent=2, ensure_ascii=False) if confirmed else "(none — no questions answered yet)",
        "",
        "## ACCEPTED ASSUMPTIONS (resolved facts with provenance — inherit into global_assumptions as 'Assumption (accepted): ...'; do NOT re-open as questions)",
        json.dumps(assumptions, indent=2, ensure_ascii=False) if assumptions else "(none)",
        "",
        "## OPEN / UNANSWERED QUESTIONS (unresolved — fold into open_questions_for_client; never invent answers)",
        json.dumps(open_questions, indent=2, ensure_ascii=False) if open_questions else "(none — everything was answered)",
        "",
        "## APPROVED PRESALES BRIEF (human-reviewed markdown)",
        presales_brief_text or "(brief not available)",
    ]
    return "\n".join(parts)


async def update_question_answers(
    presales_id: str,
    user_id: str,
    answers: dict,
    db: Session
) -> dict:
    """
    Update answers for multiple questions at once.

    Args:
        presales_id: The presales analysis ID
        user_id: The user ID
        answers: Dict mapping question_id -> answer
        db: Database session

    Returns:
        Dict with update status
    """
    from datetime import datetime

    try:
        updated_count = 0
        history_records = []

        for question_id, answer in answers.items():
            question = db.query(models.PresalesQuestion).filter(
                models.PresalesQuestion.question_id == question_id,
                models.PresalesQuestion.presales_id == presales_id,
                models.PresalesQuestion.user_id == user_id
            ).first()

            if not question:
                logger.warning(f"Question not found: {question_id}")
                continue

            # Record history
            history = models.PresalesAnswerHistory(
                question_id=question_id,
                presales_id=presales_id,
                previous_answer=question.answer,
                new_answer=answer if answer else None,
                change_type="updated" if question.answer else "created",
                changed_by=user_id
            )
            db.add(history)
            history_records.append(history)

            # Update question
            question.answer = answer if answer else None
            question.answered_at = datetime.utcnow() if answer else None
            question.answered_by = user_id if answer else None
            question.status = models.QuestionStatus.ANSWERED if answer else models.QuestionStatus.PENDING

            updated_count += 1

        db.commit()

        logger.info(f"Updated {updated_count} question answers for presales: {presales_id}")

        return {
            "updated_count": updated_count,
            "history_records": len(history_records)
        }

    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error updating question answers: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating answers: {str(e)}"
        )


async def save_question_answer(
    question_id: str,
    answer: str,
    db: Session,
    user_id: str = None
) -> dict:
    """
    Save a single answer to a question (used by chat).

    Args:
        question_id: The question ID
        answer: The answer text
        db: Database session
        user_id: Optional user ID for tracking

    Returns:
        Dict with status and question_id
    """
    from datetime import datetime

    try:
        question = db.query(models.PresalesQuestion).filter(
            models.PresalesQuestion.question_id == question_id
        ).first()

        if not question:
            logger.warning(f"Question not found for answer save: {question_id}")
            return {"success": False, "error": "Question not found"}

        # Record history if there was a previous answer
        if question.answer:
            history = models.PresalesAnswerHistory(
                question_id=question_id,
                presales_id=question.presales_id,
                previous_answer=question.answer,
                new_answer=answer,
                change_type="updated_via_chat",
                changed_by=user_id or question.user_id
            )
            db.add(history)

        # Update question
        question.answer = answer
        question.answered_at = datetime.utcnow()
        question.answered_by = user_id or question.user_id
        question.status = models.QuestionStatus.ANSWERED

        db.commit()

        logger.info(f"Saved answer for question {question_id} via chat")

        return {
            "success": True,
            "question_id": question_id,
            "question_number": question.question_number
        }

    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error saving question answer: {str(e)}")
        return {"success": False, "error": str(e)}


async def update_question_status(
    question_id: str,
    user_id: str,
    status_value: str,
    reason: str,
    invalidated_by: str,
    db: Session
) -> dict:
    """
    Update the status of a question (e.g., mark as invalid).

    Args:
        question_id: The question ID
        user_id: The user ID
        status_value: New status value
        reason: Reason for status change
        invalidated_by: Question ID that caused invalidation (if applicable)
        db: Database session

    Returns:
        Dict with status
    """
    from datetime import datetime

    try:
        question = db.query(models.PresalesQuestion).filter(
            models.PresalesQuestion.question_id == question_id,
            models.PresalesQuestion.user_id == user_id
        ).first()

        if not question:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Question not found: {question_id}"
            )

        question.status = status_value
        if status_value == models.QuestionStatus.INVALID:
            question.invalidated_reason = reason
            question.invalidated_at = datetime.utcnow()
            question.invalidated_by_question_id = invalidated_by
        elif status_value == models.QuestionStatus.NEEDS_REVIEW:
            question.restored_in_iteration = (question.restored_in_iteration or 0) + 1

        db.commit()
        db.refresh(question)

        logger.info(f"Updated question {question_id} status to: {status_value}")

        return {
            "question_id": question_id,
            "status": question.status
        }

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error updating question status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating question status: {str(e)}"
        )


async def restore_question(
    question_id: str,
    user_id: str,
    db: Session
) -> dict:
    """
    Restore an invalidated question back to needs_review status.

    Args:
        question_id: The question ID
        user_id: The user ID
        db: Database session

    Returns:
        Dict with status
    """
    try:
        question = db.query(models.PresalesQuestion).filter(
            models.PresalesQuestion.question_id == question_id,
            models.PresalesQuestion.user_id == user_id
        ).first()

        if not question:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Question not found: {question_id}"
            )

        if question.status != models.QuestionStatus.INVALID:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Question is not in invalid status"
            )

        # Restore with old answer if exists, otherwise pending
        if question.answer:
            question.status = models.QuestionStatus.NEEDS_REVIEW
        else:
            question.status = models.QuestionStatus.PENDING

        question.restored_in_iteration = (question.restored_in_iteration or 0) + 1

        db.commit()
        db.refresh(question)

        logger.info(f"Restored question {question_id} to status: {question.status}")

        return {
            "question_id": question_id,
            "status": question.status,
            "answer_preserved": question.answer is not None
        }

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error restoring question: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error restoring question: {str(e)}"
        )


async def update_presales_readiness(
    presales_id: str,
    readiness_score: float,
    readiness_status: str,
    assumptions_list: list,
    contradictions_list: list,
    vague_answers_list: list,
    db: Session
) -> dict:
    """
    Update presales analysis with readiness information.

    Args:
        presales_id: The presales analysis ID
        readiness_score: Score from 0.0 to 1.0
        readiness_status: Status string
        assumptions_list: List of assumptions
        contradictions_list: List of contradictions
        vague_answers_list: List of vague answers
        db: Database session

    Returns:
        Dict with status
    """
    try:
        presales = db.query(models.PresalesAnalysis).filter(
            models.PresalesAnalysis.presales_id == presales_id
        ).first()

        if not presales:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Presales analysis not found: {presales_id}"
            )

        presales.readiness_score = readiness_score
        presales.readiness_status = readiness_status
        presales.assumptions_list = assumptions_list
        presales.contradictions_list = contradictions_list
        presales.vague_answers_list = vague_answers_list
        presales.iteration_count = (presales.iteration_count or 1) + 1

        flag_modified(presales, "assumptions_list")
        flag_modified(presales, "contradictions_list")
        flag_modified(presales, "vague_answers_list")

        db.commit()
        db.refresh(presales)

        logger.info(f"Updated presales readiness for {presales_id}: score={readiness_score}, status={readiness_status}")

        return {
            "presales_id": presales_id,
            "readiness_score": presales.readiness_score,
            "readiness_status": presales.readiness_status,
            "iteration_count": presales.iteration_count
        }

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error updating presales readiness: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating readiness: {str(e)}"
        )


async def save_analysis_history(
    presales_id: str,
    user_id: str,
    analysis_result: dict,
    questions_snapshot: list,
    processing_time_ms: int,
    db: Session
) -> dict:
    """
    Save analysis history record for audit trail.

    Args:
        presales_id: The presales analysis ID
        user_id: The user ID who triggered analysis
        analysis_result: The analysis result dict
        questions_snapshot: Snapshot of questions with answers
        processing_time_ms: Time taken for analysis
        db: Database session

    Returns:
        Dict with history record ID
    """
    try:
        # Get current iteration count
        presales = db.query(models.PresalesAnalysis).filter(
            models.PresalesAnalysis.presales_id == presales_id
        ).first()

        iteration = presales.iteration_count if presales else 1

        history = models.PresalesAnalysisHistory(
            presales_id=presales_id,
            iteration_number=iteration,
            readiness_score=analysis_result.get("readiness", {}).get("score"),
            readiness_status=analysis_result.get("readiness", {}).get("status"),
            assumptions_made=analysis_result.get("assumptions"),
            contradictions_found=analysis_result.get("contradictions"),
            vague_answers_found=analysis_result.get("vague_answers"),
            questions_invalidated=[
                q.get("question_id") for q in analysis_result.get("invalidated_questions", [])
            ],
            answers_snapshot=questions_snapshot,
            analyzed_by=user_id,
            processing_time_ms=processing_time_ms
        )

        db.add(history)
        db.commit()
        db.refresh(history)

        logger.info(f"Saved analysis history for presales {presales_id}, iteration {iteration}")

        return {
            "analysis_history_id": history.analysis_history_id,
            "iteration_number": history.iteration_number
        }

    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error saving analysis history: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error saving analysis history: {str(e)}"
        )


async def get_presales_with_questions(
    presales_id: str,
    user_id: str,
    db: Session
) -> dict:
    """
    Get presales analysis with all questions.

    Args:
        presales_id: The presales analysis ID
        user_id: The user ID
        db: Database session

    Returns:
        Dict with presales data and questions
    """
    try:
        presales = db.query(models.PresalesAnalysis).filter(
            models.PresalesAnalysis.presales_id == presales_id,
            models.PresalesAnalysis.user_id == user_id
        ).first()

        if not presales:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Presales analysis not found: {presales_id}"
            )

        questions = await get_presales_questions(presales_id, user_id, db)

        return {
            "presales_id": presales.presales_id,
            "document_id": presales.document_id,
            "presales_brief": presales.presales_brief,
            "readiness_score": presales.readiness_score,
            "readiness_status": presales.readiness_status,
            "assumptions_list": presales.assumptions_list or [],
            "contradictions_list": presales.contradictions_list or [],
            "vague_answers_list": presales.vague_answers_list or [],
            "iteration_count": presales.iteration_count,
            "status": presales.status,
            "questions": questions,
            "created_at": presales.created_at.isoformat() if presales.created_at else None
        }

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Error getting presales with questions: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving presales: {str(e)}"
        )


# ============================================================================
# PENDING ACTIONS - For Conversation State Management
# ============================================================================

async def load_pending_actions(chat_history_id: str, db: Session) -> list:
    """
    Load all pending actions for a chat session from the database.

    Args:
        chat_history_id: The chat history ID
        db: Database session

    Returns:
        List of pending action dictionaries
    """
    try:
        actions = db.query(models.PendingAction).filter(
            models.PendingAction.chat_history_id == chat_history_id
        ).order_by(models.PendingAction.created_at).all()

        return [
            {
                "action_id": a.id,
                "action_type": a.action_type,
                "content": a.content,
                "context": a.context,
                "category": a.category,
                "awaiting_response": a.awaiting_response,
                "resolution": a.resolution,
                "created_at": a.created_at.isoformat() if a.created_at else None
            }
            for a in actions
        ]

    except SQLAlchemyError as e:
        logger.error(f"Error loading pending actions: {str(e)}")
        return []


async def save_pending_action(
    chat_history_id: str,
    action_id: str,
    action_type: str,
    content: str,
    db: Session,
    context: str = None,
    category: str = None
) -> dict:
    """
    Save a new pending action to the database.

    Args:
        chat_history_id: The chat history ID
        action_id: The action ID (e.g., "PA-001")
        action_type: Type of action (suggestion, rollback, clear_all)
        content: What the action does
        db: Database session
        context: Why this was offered
        category: Change category (modify_architecture, etc.)

    Returns:
        Dict with action details
    """
    try:
        pending_action = models.PendingAction(
            id=action_id,
            chat_history_id=chat_history_id,
            action_type=action_type,
            content=content,
            context=context,
            category=category,
            awaiting_response=True
        )

        db.add(pending_action)
        db.commit()
        db.refresh(pending_action)

        logger.info(f"Saved pending action {action_id} for chat {chat_history_id}")

        return {
            "action_id": pending_action.id,
            "action_type": pending_action.action_type,
            "content": pending_action.content,
            "awaiting_response": pending_action.awaiting_response
        }

    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error saving pending action: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error saving pending action: {str(e)}"
        )


async def resolve_pending_action(
    action_id: str,
    chat_history_id: str,
    resolution: str,
    db: Session,
    resolution_message: str = None
) -> dict:
    """
    Resolve a pending action (confirm, decline, expire, supersede).

    Args:
        action_id: The action ID to resolve
        chat_history_id: The chat history ID
        resolution: The resolution type (confirmed, declined, expired, superseded)
        db: Database session
        resolution_message: Optional message about conditions

    Returns:
        Dict with resolution details
    """
    from datetime import datetime

    try:
        action = db.query(models.PendingAction).filter(
            models.PendingAction.id == action_id,
            models.PendingAction.chat_history_id == chat_history_id
        ).first()

        if not action:
            logger.warning(f"Pending action {action_id} not found for resolution")
            return {"status": "not_found", "action_id": action_id}

        action.awaiting_response = False
        action.resolution = resolution
        action.resolution_message = resolution_message
        action.resolved_at = datetime.now()

        db.commit()

        logger.info(f"Resolved pending action {action_id} as {resolution}")

        return {
            "status": "resolved",
            "action_id": action_id,
            "resolution": resolution,
            "content": action.content
        }

    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error resolving pending action: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error resolving pending action: {str(e)}"
        )


async def get_active_pending_actions(chat_history_id: str, db: Session) -> list:
    """
    Get only pending actions that are still awaiting response.

    Args:
        chat_history_id: The chat history ID
        db: Database session

    Returns:
        List of active pending action dictionaries
    """
    try:
        actions = db.query(models.PendingAction).filter(
            models.PendingAction.chat_history_id == chat_history_id,
            models.PendingAction.awaiting_response == True
        ).order_by(models.PendingAction.created_at).all()

        return [
            {
                "action_id": a.id,
                "action_type": a.action_type,
                "content": a.content,
                "context": a.context,
                "category": a.category,
                "created_at": a.created_at.isoformat() if a.created_at else None
            }
            for a in actions
        ]

    except SQLAlchemyError as e:
        logger.error(f"Error getting active pending actions: {str(e)}")
        return []


async def get_next_pending_action_id(chat_history_id: str, db: Session) -> str:
    """
    Get the next available pending action ID for a chat session.

    Args:
        chat_history_id: The chat history ID
        db: Database session

    Returns:
        Next action ID (e.g., "PA-003" if PA-001 and PA-002 exist)
    """
    try:
        actions = db.query(models.PendingAction).filter(
            models.PendingAction.chat_history_id == chat_history_id
        ).all()

        max_num = 0
        for action in actions:
            try:
                num = int(action.id.split('-')[1])
                max_num = max(max_num, num)
            except (IndexError, ValueError):
                pass

        return f"PA-{max_num + 1:03d}"

    except SQLAlchemyError as e:
        logger.error(f"Error getting next action ID: {str(e)}")
        return "PA-001"


async def clear_pending_actions(chat_history_id: str, db: Session) -> int:
    """
    Clear all pending actions for a chat session (typically when conversation ends or resets).

    Args:
        chat_history_id: The chat history ID
        db: Database session

    Returns:
        Number of actions cleared
    """
    from datetime import datetime

    try:
        count = db.query(models.PendingAction).filter(
            models.PendingAction.chat_history_id == chat_history_id,
            models.PendingAction.awaiting_response == True
        ).update({
            "awaiting_response": False,
            "resolution": "expired",
            "resolved_at": datetime.now()
        })

        db.commit()
        logger.info(f"Cleared {count} pending actions for chat {chat_history_id}")
        return count

    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error clearing pending actions: {str(e)}")
        return 0


async def find_duplicate_changes(changes: list, threshold: float = 0.6) -> list:
    """
    Find groups of similar/duplicate changes using Jaccard similarity.

    Uses word overlap to detect potential duplicates without requiring embeddings.
    Changes with similarity above threshold are grouped together.

    Args:
        changes: List of change dictionaries with 'id' and 'user_request' fields
        threshold: Similarity threshold (0-1). Default 0.6 (60% overlap)

    Returns:
        List of duplicate groups:
        [
            {
                "ids": ["CHG-001", "CHG-003"],
                "similarity": 0.75,
                "preview": "Use PostgreSQL instead of..."
            }
        ]
    """
    if not changes or len(changes) < 2:
        return []

    duplicates = []
    processed = set()

    for i, change1 in enumerate(changes):
        change1_id = change1.get('id', change1.get('change_id', ''))
        if change1_id in processed:
            continue

        group = [change1_id]
        request1 = change1.get('user_request', change1.get('content', ''))
        words1 = set(request1.lower().split())

        if len(words1) < 2:
            continue

        max_similarity = 0

        for j, change2 in enumerate(changes[i+1:], i+1):
            change2_id = change2.get('id', change2.get('change_id', ''))
            if change2_id in processed:
                continue

            request2 = change2.get('user_request', change2.get('content', ''))
            words2 = set(request2.lower().split())

            if len(words2) < 2:
                continue

            # Jaccard similarity
            intersection = len(words1 & words2)
            union = len(words1 | words2)
            similarity = intersection / union if union > 0 else 0

            if similarity >= threshold:
                group.append(change2_id)
                processed.add(change2_id)
                max_similarity = max(max_similarity, similarity)

        if len(group) > 1:
            duplicates.append({
                "ids": group,
                "similarity": round(max_similarity, 2),
                "preview": request1[:60] + "..." if len(request1) > 60 else request1
            })
            processed.add(change1_id)

    logger.info(f"Found {len(duplicates)} duplicate groups from {len(changes)} changes")
    return duplicates


async def merge_pending_changes(
    chat_history_id: str,
    change_ids: list,
    merged_content: str,
    db: Session
) -> dict:
    """
    Merge multiple pending changes into one consolidated change.

    This removes the specified changes and creates a new merged change that
    combines their affected sections and tracks the source changes.

    Args:
        chat_history_id: The chat history ID
        change_ids: List of change IDs to merge (e.g., ["CHG-001", "CHG-003"])
        merged_content: The consolidated user request text
        db: Database session

    Returns:
        {
            "status": "success|error",
            "removed_ids": ["CHG-001", "CHG-003"],
            "new_change": {...},
            "message": "..."
        }
    """
    import copy
    from datetime import datetime

    try:
        # Get current report version with pending changes
        record = db.query(models.ReportVersions).filter(
            models.ReportVersions.chat_history_id == chat_history_id
        ).order_by(models.ReportVersions.version.desc()).first()

        if not record:
            return {
                "status": "error",
                "message": f"No report found for chat {chat_history_id}"
            }

        current_changes = copy.deepcopy(record.pending_changes or [])

        if not current_changes:
            return {
                "status": "error",
                "message": "No pending changes to merge"
            }

        # Find the changes to merge
        changes_to_merge = [c for c in current_changes if c.get('id') in change_ids]

        if len(changes_to_merge) < 2:
            return {
                "status": "error",
                "message": f"Need at least 2 changes to merge, found {len(changes_to_merge)}"
            }

        # Extract affected sections from all changes being merged
        affected_sections = set()
        change_types = set()
        for change in changes_to_merge:
            sections = change.get('affected_sections', [])
            if isinstance(sections, list):
                affected_sections.update(sections)
            change_types.add(change.get('type', 'modify_architecture'))

        # Remove the old changes
        remaining_changes = [c for c in current_changes if c.get('id') not in change_ids]

        # Generate new change ID
        max_num = 0
        for change in current_changes:
            try:
                num = int(change.get('id', '').split('-')[1])
                max_num = max(max_num, num)
            except (IndexError, ValueError):
                pass
        new_id = f"CHG-{max_num + 1:03d}"

        # Create merged change
        merged_change = {
            "id": new_id,
            "type": list(change_types)[0] if len(change_types) == 1 else "modify_architecture",
            "user_request": merged_content,
            "affected_sections": list(affected_sections),
            "timestamp": datetime.now().isoformat(),
            "merged_from": change_ids,
            "status": "pending"
        }

        remaining_changes.append(merged_change)

        # Save to database
        record.pending_changes = remaining_changes
        flag_modified(record, "pending_changes")
        db.commit()

        logger.info(f"Merged changes {change_ids} into {new_id}")

        return {
            "status": "success",
            "removed_ids": change_ids,
            "new_change": merged_change,
            "message": f"Successfully merged {len(change_ids)} changes into {new_id}"
        }

    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error merging pending changes: {str(e)}")
        return {
            "status": "error",
            "message": f"Database error: {str(e)}"
        }


async def remove_pending_change(
    chat_history_id: str,
    change_id: str,
    db: Session
) -> dict:
    """
    Remove a specific pending change by ID.

    Args:
        chat_history_id: The chat history ID
        change_id: The change ID to remove (e.g., "CHG-001")
        db: Database session

    Returns:
        {
            "status": "success|error",
            "removed_change": {...},
            "remaining_count": int,
            "message": "..."
        }
    """
    import copy

    try:
        record = db.query(models.ReportVersions).filter(
            models.ReportVersions.chat_history_id == chat_history_id
        ).order_by(models.ReportVersions.version_number.desc()).first()

        if not record:
            return {
                "status": "error",
                "message": f"No report found for chat {chat_history_id}"
            }

        current_changes = copy.deepcopy(record.pending_changes or [])

        # Find and remove the specified change
        removed_change = None
        remaining_changes = []

        for change in current_changes:
            if change.get('id') == change_id:
                removed_change = change
            else:
                remaining_changes.append(change)

        if not removed_change:
            return {
                "status": "error",
                "message": f"Change {change_id} not found in pending changes"
            }

        # Save to database
        record.pending_changes = remaining_changes
        flag_modified(record, "pending_changes")
        db.commit()

        logger.info(f"Removed pending change {change_id}")

        return {
            "status": "success",
            "removed_change": removed_change,
            "remaining_count": len(remaining_changes),
            "message": f"Successfully removed {change_id}"
        }

    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error removing pending change: {str(e)}")
        return {
            "status": "error",
            "message": f"Database error: {str(e)}"
        }


# ============================================================
# TRANSACTION HISTORY FOR UNDO/REDO OPERATIONS
# ============================================================

async def record_transaction(
    chat_history_id: str,
    action_type: str,
    action_data: dict,
    description: str,
    db: Session
) -> dict:
    """
    Record a reversible transaction for undo/redo functionality.

    Args:
        chat_history_id: The chat history ID
        action_type: Type of action (add_change, remove_change, merge_changes, etc.)
        action_data: Data needed to reverse/redo the action
        description: Human-readable description
        db: Database session

    Returns:
        Dict with transaction ID and status
    """
    try:
        # Get the next sequence number for this chat
        last_tx = db.query(models.TransactionHistory).filter(
            models.TransactionHistory.chat_history_id == chat_history_id
        ).order_by(models.TransactionHistory.sequence_number.desc()).first()

        next_sequence = (last_tx.sequence_number + 1) if last_tx else 1

        # Clear any undone transactions (they can no longer be redone after new action)
        db.query(models.TransactionHistory).filter(
            models.TransactionHistory.chat_history_id == chat_history_id,
            models.TransactionHistory.is_undone == True
        ).delete()

        # Create new transaction record
        transaction = models.TransactionHistory(
            id=new_id(),
            chat_history_id=chat_history_id,
            action_type=action_type,
            action_description=description,
            action_data=action_data,
            sequence_number=next_sequence
        )

        db.add(transaction)
        db.commit()
        db.refresh(transaction)

        logger.info(f"Recorded transaction {transaction.id}: {action_type} - {description}")

        return {
            "status": "success",
            "transaction_id": transaction.id,
            "sequence_number": next_sequence
        }

    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error recording transaction: {str(e)}")
        return {
            "status": "error",
            "message": f"Failed to record transaction: {str(e)}"
        }


async def get_undo_stack(chat_history_id: str, db: Session) -> list:
    """
    Get the stack of transactions that can be undone (not yet undone).

    Returns:
        List of transactions ordered by most recent first
    """
    try:
        transactions = db.query(models.TransactionHistory).filter(
            models.TransactionHistory.chat_history_id == chat_history_id,
            models.TransactionHistory.is_undone == False
        ).order_by(models.TransactionHistory.sequence_number.desc()).all()

        return [
            {
                "id": tx.id,
                "action_type": tx.action_type,
                "description": tx.action_description,
                "action_data": tx.action_data,
                "sequence_number": tx.sequence_number,
                "created_at": tx.created_at.isoformat() if tx.created_at else None
            }
            for tx in transactions
        ]

    except SQLAlchemyError as e:
        logger.error(f"Error getting undo stack: {str(e)}")
        return []


async def get_redo_stack(chat_history_id: str, db: Session) -> list:
    """
    Get the stack of transactions that can be redone (currently undone).

    Returns:
        List of transactions ordered by most recently undone first
    """
    try:
        transactions = db.query(models.TransactionHistory).filter(
            models.TransactionHistory.chat_history_id == chat_history_id,
            models.TransactionHistory.is_undone == True
        ).order_by(models.TransactionHistory.sequence_number.desc()).all()

        return [
            {
                "id": tx.id,
                "action_type": tx.action_type,
                "description": tx.action_description,
                "action_data": tx.action_data,
                "sequence_number": tx.sequence_number,
                "undone_at": tx.undone_at.isoformat() if tx.undone_at else None
            }
            for tx in transactions
        ]

    except SQLAlchemyError as e:
        logger.error(f"Error getting redo stack: {str(e)}")
        return []


async def undo_last_transaction(chat_history_id: str, db: Session) -> dict:
    """
    Undo the last transaction and return the data needed to reverse it.

    Returns:
        Dict with action_type, action_data, and status
    """
    from datetime import datetime

    try:
        # Get the most recent non-undone transaction
        transaction = db.query(models.TransactionHistory).filter(
            models.TransactionHistory.chat_history_id == chat_history_id,
            models.TransactionHistory.is_undone == False
        ).order_by(models.TransactionHistory.sequence_number.desc()).first()

        if not transaction:
            return {
                "status": "nothing_to_undo",
                "message": "No transactions to undo"
            }

        # Mark as undone
        transaction.is_undone = True
        transaction.undone_at = datetime.now()
        db.commit()

        logger.info(f"Undone transaction {transaction.id}: {transaction.action_description}")

        return {
            "status": "success",
            "transaction_id": transaction.id,
            "action_type": transaction.action_type,
            "action_data": transaction.action_data,
            "description": transaction.action_description
        }

    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error undoing transaction: {str(e)}")
        return {
            "status": "error",
            "message": f"Failed to undo: {str(e)}"
        }


async def undo_specific_transaction(chat_history_id: str, change_id: str, db: Session) -> dict:
    """
    Undo a specific change by its CHG-XXX ID.

    Args:
        chat_history_id: The chat history ID
        change_id: The change ID (e.g., "CHG-003")
        db: Database session

    Returns:
        Dict with action_type, action_data, and status
    """
    from datetime import datetime

    try:
        # Find the transaction that added this change
        transactions = db.query(models.TransactionHistory).filter(
            models.TransactionHistory.chat_history_id == chat_history_id,
            models.TransactionHistory.is_undone == False
        ).all()

        target_tx = None
        for tx in transactions:
            action_data = tx.action_data or {}
            if action_data.get("change_id") == change_id:
                target_tx = tx
                break

        if not target_tx:
            return {
                "status": "not_found",
                "message": f"No transaction found for {change_id}"
            }

        # Mark as undone
        target_tx.is_undone = True
        target_tx.undone_at = datetime.now()
        db.commit()

        logger.info(f"Undone specific transaction for {change_id}")

        return {
            "status": "success",
            "transaction_id": target_tx.id,
            "action_type": target_tx.action_type,
            "action_data": target_tx.action_data,
            "description": target_tx.action_description
        }

    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error undoing specific transaction: {str(e)}")
        return {
            "status": "error",
            "message": f"Failed to undo: {str(e)}"
        }


async def redo_last_transaction(chat_history_id: str, db: Session) -> dict:
    """
    Redo the most recently undone transaction.

    Returns:
        Dict with action_type, action_data, and status
    """
    from datetime import datetime

    try:
        # Get the most recently undone transaction
        transaction = db.query(models.TransactionHistory).filter(
            models.TransactionHistory.chat_history_id == chat_history_id,
            models.TransactionHistory.is_undone == True
        ).order_by(models.TransactionHistory.sequence_number.desc()).first()

        if not transaction:
            return {
                "status": "nothing_to_redo",
                "message": "No transactions to redo"
            }

        # Mark as not undone (redone)
        transaction.is_undone = False
        transaction.redone_at = datetime.now()
        db.commit()

        logger.info(f"Redone transaction {transaction.id}: {transaction.action_description}")

        return {
            "status": "success",
            "transaction_id": transaction.id,
            "action_type": transaction.action_type,
            "action_data": transaction.action_data,
            "description": transaction.action_description
        }

    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error redoing transaction: {str(e)}")
        return {
            "status": "error",
            "message": f"Failed to redo: {str(e)}"
        }


async def get_transaction_history(chat_history_id: str, db: Session, limit: int = 20) -> list:
    """
    Get the full transaction history for a chat session.

    Returns:
        List of all transactions ordered by sequence
    """
    try:
        transactions = db.query(models.TransactionHistory).filter(
            models.TransactionHistory.chat_history_id == chat_history_id
        ).order_by(models.TransactionHistory.sequence_number.desc()).limit(limit).all()

        return [
            {
                "id": tx.id,
                "action_type": tx.action_type,
                "description": tx.action_description,
                "is_undone": tx.is_undone,
                "sequence_number": tx.sequence_number,
                "created_at": tx.created_at.isoformat() if tx.created_at else None,
                "undone_at": tx.undone_at.isoformat() if tx.undone_at else None,
                "redone_at": tx.redone_at.isoformat() if tx.redone_at else None
            }
            for tx in transactions
        ]

    except SQLAlchemyError as e:
        logger.error(f"Error getting transaction history: {str(e)}")
        return []


# ============================================================
# REPORT REGENERATION CONTEXT
# ============================================================

async def get_regeneration_context(
    chat_history_id: str,
    user_id: str,
    db: Session
) -> dict:
    """
    Get ALL context needed for full report regeneration, including presales data.

    This function retrieves:
    - Analysis link (presales_id, document_id, user_answers)
    - Presales analysis (scanned_requirements, blind_spots, assumptions, etc.)
    - Presales questions with answers
    - Pending changes from current report version
    - Current report summary

    Args:
        chat_history_id: The chat history ID
        user_id: The user ID (for security filtering)
        db: Database session

    Returns:
        {
            "presales_id": str or None,
            "document_id": str,
            "document_text": str,              # JSON of extracted_requirements
            "scanned_requirements": dict,
            "blind_spots": dict,
            "assumptions_list": list,          # Assumptions from presales
            "questions_and_answers": list,     # Q&A from presales questions
            "additional_context": str,         # User comments/context (from user_answers)
            "user_answers": dict,              # Answers from AnalysisLink
            "pending_changes": list,
            "current_report_summary": dict,
            "current_version": int
        }

    Raises:
        HTTPException: If chat_history not found or access denied
    """
    import json

    try:
        # Step 1: Get AnalysisLink by chat_history_id
        analysis_link = db.query(models.AnalysisLink).filter(
            models.AnalysisLink.chat_history_id == chat_history_id,
            models.AnalysisLink.user_id == user_id
        ).first()

        presales_id = None
        presales_data = {}
        questions_and_answers = []
        user_answers = {}

        if analysis_link:
            presales_id = analysis_link.presales_id
            user_answers = analysis_link.user_answers or {}

            # Step 2: Get PresalesAnalysis if presales_id exists
            if presales_id:
                presales = db.query(models.PresalesAnalysis).filter(
                    models.PresalesAnalysis.presales_id == presales_id,
                    models.PresalesAnalysis.user_id == user_id
                ).first()

                if presales:
                    presales_data = {
                        "extracted_requirements": presales.extracted_requirements or {},
                        "blind_spots": presales.blind_spots or {},
                        "p1_blockers": presales.p1_blockers or {},
                        "technology_risks": presales.technology_risks or {},
                        "assumptions_list": presales.assumptions_list or [],
                        "contradictions_list": presales.contradictions_list or [],
                        "presales_brief": presales.presales_brief or ""
                    }

                # Step 3: Get PresalesQuestions with answers
                questions = db.query(models.PresalesQuestion).filter(
                    models.PresalesQuestion.presales_id == presales_id,
                    models.PresalesQuestion.user_id == user_id,
                    models.PresalesQuestion.status != models.QuestionStatus.INVALID
                ).order_by(models.PresalesQuestion.display_order).all()

                questions_and_answers = [
                    {
                        "question_id": q.question_id,
                        "question_number": q.question_number,
                        "question_type": q.question_type,
                        "area_or_category": q.area_or_category,
                        "title": q.title,
                        "question_text": q.question_text,
                        "answer": q.answer,
                        "answer_quality": q.answer_quality
                    }
                    for q in questions if q.answer  # Only include answered questions
                ]

        # Step 4: Get document_id from ChatHistory if not from AnalysisLink
        document_id = analysis_link.document_id if analysis_link else None
        if not document_id:
            chat_history = db.query(models.ChatHistory).filter(
                models.ChatHistory.chat_history_id == chat_history_id,
                models.ChatHistory.user_id == user_id
            ).first()
            if chat_history:
                document_id = chat_history.document_id
            else:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Chat history not found: {chat_history_id}"
                )

        # Step 5: Get pending changes and current report from ReportVersions
        report_version = db.query(models.ReportVersions).filter(
            models.ReportVersions.chat_history_id == chat_history_id
        ).order_by(models.ReportVersions.created_at.desc()).first()

        pending_changes = []
        current_report_summary = {}
        current_version = 0
        previous_version_id = None

        if report_version:
            pending_changes = copy.deepcopy(report_version.pending_changes) if report_version.pending_changes else []
            current_report_summary = report_version.summary_report or {}
            current_version = report_version.version_number or 1
            previous_version_id = report_version.report_version_id  # Track the parent version

        # Build document_text from extracted_requirements (as done in services.py)
        document_text = json.dumps(presales_data.get("extracted_requirements", {}))

        # Extract additional_context from user_answers if present
        additional_context = user_answers.get("additional_context", "") if user_answers else ""

        logger.info(
            f"Regeneration context retrieved for chat_history_id: {chat_history_id}, "
            f"presales_id: {presales_id}, questions: {len(questions_and_answers)}, "
            f"pending_changes: {len(pending_changes)}"
        )

        return {
            "presales_id": presales_id,
            "document_id": document_id,
            "document_text": document_text,
            "scanned_requirements": presales_data.get("extracted_requirements", {}),
            "blind_spots": presales_data.get("blind_spots", {}),
            "p1_blockers": presales_data.get("p1_blockers", {}),
            "technology_risks": presales_data.get("technology_risks", {}),
            "assumptions_list": presales_data.get("assumptions_list", []),
            "contradictions_list": presales_data.get("contradictions_list", []),
            "presales_brief": presales_data.get("presales_brief", ""),
            "questions_and_answers": questions_and_answers,
            "additional_context": additional_context,
            "user_answers": user_answers,
            "pending_changes": pending_changes,
            "current_report_summary": current_report_summary,
            "current_version": current_version,
            # Changelog tracking fields
            "previous_version_id": previous_version_id,
            "previous_summary": current_report_summary  # Same as current_report_summary for comparison
        }

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Error getting regeneration context: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving regeneration context: {str(e)}"
        )


# ============================================================
# PROJECTS OVERVIEW AGGREGATION (for /projects/overview page)
# ============================================================

async def fetch_projects_overview(user_id: str, db: Session) -> dict:
    """
    Aggregate everything the Projects Overview page needs in one pass:
      - KPI block (total/presales/full counts, avg readiness, 7d trend)
      - Per-project rows with readiness, question counts, pending-change count,
        report-version count, last message preview
      - Cross-project questions_inbox of pending / needs_review questions

    Returns a dict ready to be merged with subscription data by the router.
    """
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import func, case

    try:
        # --- 1. Load all active chats for the user -------------------------
        chats = (
            db.query(models.ChatHistory)
            .filter(
                models.ChatHistory.user_id == user_id,
                models.ChatHistory.active_tag == "True",
            )
            .order_by(models.ChatHistory.modified_at.desc())
            .all()
        )

        chat_ids = [c.chat_history_id for c in chats]

        # Empty state -- no projects yet
        if not chat_ids:
            return {
                "kpis": {
                    "total_projects": 0,
                    "presales_count": 0,
                    "full_report_count": 0,
                    "avg_readiness": 0.0,
                    "readiness_trend_7d": 0.0,
                },
                "projects": [],
                "questions_inbox": [],
            }

        # --- 2. AnalysisLink -> analysis_mode + presales_id per chat --------
        links = (
            db.query(models.AnalysisLink)
            .filter(models.AnalysisLink.chat_history_id.in_(chat_ids))
            .all()
        )
        link_by_chat = {l.chat_history_id: l for l in links}

        presales_ids = [l.presales_id for l in links if l.presales_id]

        # --- 3. PresalesAnalysis rows (for readiness scores) ---------------
        presales_rows = {}
        if presales_ids:
            for pa in (
                db.query(models.PresalesAnalysis)
                .filter(models.PresalesAnalysis.presales_id.in_(presales_ids))
                .all()
            ):
                presales_rows[pa.presales_id] = pa

        # --- 4. Question summary counts per presales_id ---------------------
        # Group by presales_id, question_type, status to build summary
        question_counts: dict = {}
        vague_counts: dict = {}
        if presales_ids:
            rows = (
                db.query(
                    models.PresalesQuestion.presales_id,
                    models.PresalesQuestion.question_type,
                    models.PresalesQuestion.status,
                    func.count(models.PresalesQuestion.question_id).label("cnt"),
                )
                .filter(models.PresalesQuestion.presales_id.in_(presales_ids))
                .group_by(
                    models.PresalesQuestion.presales_id,
                    models.PresalesQuestion.question_type,
                    models.PresalesQuestion.status,
                )
                .all()
            )
            for presales_id, qtype, qstatus, cnt in rows:
                bucket = question_counts.setdefault(presales_id, {})
                type_bucket = bucket.setdefault(qtype, {"total": 0, "answered": 0})
                type_bucket["total"] += cnt
                if qstatus == "answered":
                    type_bucket["answered"] += cnt

            vague_rows = (
                db.query(
                    models.PresalesQuestion.presales_id,
                    func.count(models.PresalesQuestion.question_id).label("cnt"),
                )
                .filter(
                    models.PresalesQuestion.presales_id.in_(presales_ids),
                    models.PresalesQuestion.answer_quality == "vague",
                )
                .group_by(models.PresalesQuestion.presales_id)
                .all()
            )
            vague_counts = {pid: cnt for pid, cnt in vague_rows}

        # Which presales have CLIENT-submitted answers (autosave or final) — drives the
        # "client started" dashboard status (distinct from "submitted").
        client_started_ids: set = set()
        if presales_ids:
            for (pid,) in (
                db.query(models.PresalesQuestion.presales_id)
                .filter(
                    models.PresalesQuestion.presales_id.in_(presales_ids),
                    models.PresalesQuestion.answered_by == "client",
                )
                .distinct()
                .all()
            ):
                client_started_ids.add(pid)

        # --- 5. Default ReportVersion per chat (for pending_changes count) --
        default_versions = (
            db.query(models.ReportVersions)
            .filter(
                models.ReportVersions.chat_history_id.in_(chat_ids),
                models.ReportVersions.is_default == True,
            )
            .all()
        )
        default_by_chat = {v.chat_history_id: v for v in default_versions}

        # --- 6. Report version counts per chat ------------------------------
        version_count_rows = (
            db.query(
                models.ReportVersions.chat_history_id,
                func.count(models.ReportVersions.report_version_id).label("cnt"),
            )
            .filter(models.ReportVersions.chat_history_id.in_(chat_ids))
            .group_by(models.ReportVersions.chat_history_id)
            .all()
        )
        version_counts = {cid: cnt for cid, cnt in version_count_rows}

        # --- 6b. Pipeline status per chat (for /full-pipeline progress) ----
        pipeline_status_map = await get_pipeline_status_map(chat_ids, db)

        # --- 7. Assemble per-project rows -----------------------------------
        projects = []
        readiness_scores_all = []
        readiness_scores_last_7d = []
        readiness_scores_older = []
        now = datetime.now(timezone.utc)
        seven_days_ago = now - timedelta(days=7)

        presales_count = 0
        full_count = 0

        for c in chats:
            link = link_by_chat.get(c.chat_history_id)
            presales_id = link.presales_id if link else None
            analysis_mode = "full"
            if link and not link.full_report_generated and presales_id:
                analysis_mode = "presales"
            if analysis_mode == "presales":
                presales_count += 1
            else:
                full_count += 1

            pa = presales_rows.get(presales_id) if presales_id else None
            readiness_score = float(pa.readiness_score) if pa and pa.readiness_score is not None else 0.0
            readiness_status = pa.readiness_status if pa else "not_analyzed"

            if pa and pa.readiness_score is not None:
                readiness_scores_all.append(readiness_score)
                # Use chat.modified_at to split 7d window
                mod = c.modified_at
                if mod is not None:
                    if mod.tzinfo is None:
                        mod = mod.replace(tzinfo=timezone.utc)
                    if mod >= seven_days_ago:
                        readiness_scores_last_7d.append(readiness_score)
                    else:
                        readiness_scores_older.append(readiness_score)

            qcounts = question_counts.get(presales_id, {}) if presales_id else {}
            p1 = qcounts.get("p1_blocker", {"total": 0, "answered": 0})
            kick = qcounts.get("kickstart", {"total": 0, "answered": 0})

            default_v = default_by_chat.get(c.chat_history_id)
            pending_list = (default_v.pending_changes if default_v and default_v.pending_changes else []) or []
            pending_total = len(pending_list) if isinstance(pending_list, list) else 0

            # Last message preview from stored JSON string
            last_preview = ""
            try:
                if c.message:
                    import json as _json
                    msgs = _json.loads(c.message) if isinstance(c.message, str) else c.message
                    if isinstance(msgs, list) and msgs:
                        tail = msgs[-1]
                        last_preview = (tail.get("content", "") or "")[:180]
            except Exception:
                last_preview = ""

            # Client-questionnaire status for the dashboard badge.
            q_status = "none"
            if pa:
                if pa.client_submitted_at:
                    q_status = "submitted"
                elif presales_id in client_started_ids:
                    q_status = "started"
                elif pa.client_link_shared_at or pa.client_share_token:
                    q_status = "sent"

            projects.append({
                "chat_history_id": c.chat_history_id,
                "document_id": c.document_id,
                "title": c.title or "Untitled project",
                "custom_title": c.custom_title,
                "questionnaire_status": q_status,
                "client_submitted_at": pa.client_submitted_at.isoformat() if (pa and pa.client_submitted_at) else None,
                "analysis_mode": analysis_mode,
                "presales_id": presales_id,
                "full_report_generated": bool(link.full_report_generated) if link else False,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "modified_at": c.modified_at.isoformat() if c.modified_at else None,
                "readiness": {
                    "score": readiness_score,
                    "status": readiness_status,
                },
                "questions_summary": {
                    "p1_total": p1["total"],
                    "p1_answered": p1["answered"],
                    "kickstart_total": kick["total"],
                    "kickstart_answered": kick["answered"],
                    "vague_count": int(vague_counts.get(presales_id, 0)) if presales_id else 0,
                },
                "pending_changes": {
                    "total": pending_total,
                    "has_conflicts": False,  # Conflict detection is on-demand elsewhere
                },
                "report_versions": int(version_counts.get(c.chat_history_id, 0)),
                "last_message_preview": last_preview,
                "pipeline_status": pipeline_status_map.get(c.chat_history_id, "idle"),
            })

        # --- 8. KPI aggregation --------------------------------------------
        avg_readiness = (
            sum(readiness_scores_all) / len(readiness_scores_all)
            if readiness_scores_all else 0.0
        )
        avg_last_7d = (
            sum(readiness_scores_last_7d) / len(readiness_scores_last_7d)
            if readiness_scores_last_7d else 0.0
        )
        avg_older = (
            sum(readiness_scores_older) / len(readiness_scores_older)
            if readiness_scores_older else 0.0
        )
        readiness_trend_7d = round(avg_last_7d - avg_older, 4) if readiness_scores_older else 0.0

        kpis = {
            "total_projects": len(chats),
            "presales_count": presales_count,
            "full_report_count": full_count,
            "avg_readiness": round(avg_readiness, 4),
            "readiness_trend_7d": readiness_trend_7d,
        }

        # --- 9. Questions inbox (pending / needs_review, P1 first) ---------
        questions_inbox: list = []
        if presales_ids:
            inbox_rows = (
                db.query(models.PresalesQuestion, models.ChatHistory.chat_history_id, models.ChatHistory.title)
                .join(
                    models.AnalysisLink,
                    models.AnalysisLink.presales_id == models.PresalesQuestion.presales_id,
                )
                .join(
                    models.ChatHistory,
                    models.ChatHistory.chat_history_id == models.AnalysisLink.chat_history_id,
                )
                .filter(
                    models.PresalesQuestion.presales_id.in_(presales_ids),
                    models.PresalesQuestion.status.in_(["pending", "needs_review"]),
                )
                .order_by(
                    case((models.PresalesQuestion.question_type == "p1_blocker", 0), else_=1),
                    models.PresalesQuestion.updated_at.desc().nullslast(),
                    models.PresalesQuestion.created_at.desc(),
                )
                .limit(50)
                .all()
            )
            for q, chat_id, chat_title in inbox_rows:
                questions_inbox.append({
                    "question_id": q.question_id,
                    "chat_history_id": chat_id,
                    "project_title": chat_title or "Untitled project",
                    "presales_id": q.presales_id,
                    "question_number": q.question_number,
                    "question_type": q.question_type,
                    "title": q.title,
                    "question_text": q.question_text,
                    "status": q.status,
                    "area_or_category": q.area_or_category,
                })

        return {
            "kpis": kpis,
            "projects": projects,
            "questions_inbox": questions_inbox,
        }

    except SQLAlchemyError as e:
        logger.error(f"Error building projects overview for user {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error building projects overview: {str(e)}"
        )


# ============================================================================
# PIPELINE RUNS (9-agent full-pipeline async execution tracking)
# ============================================================================

PIPELINE_STAGES_ORDER = [
    "requirements_analyzer",
    "ambiguity_resolver",
    "validator_agent",
    "solution_architectures",
    "critic_agent",
    "evidence_gather_agent",
    "feasibility_estimator",
    "ba_final_report_generation",
]

# Stages for the contract pipeline (USE_CONTRACT_PIPELINE=true). Kept here next
# to PIPELINE_STAGES_ORDER so it's obvious both lists drive the same UI surface
# and the same pipeline_runs.stages_completed JSONB column.
CONTRACT_PIPELINE_STAGES_ORDER = [
    "plan",
    "research",
    "decide",
    "write_sections",
    "judge_and_finalize",
]


def stages_order_for_mode(use_contract_pipeline: bool) -> list[str]:
    """Pick the stage list the runner / frontend should drive against."""
    return CONTRACT_PIPELINE_STAGES_ORDER if use_contract_pipeline else PIPELINE_STAGES_ORDER


def _serialize_pipeline_run(run: "models.PipelineRun") -> dict:
    return {
        "run_id": run.run_id,
        "chat_history_id": run.chat_history_id,
        "user_id": run.user_id,
        "status": run.status,
        "current_stage": run.current_stage,
        "stages_completed": run.stages_completed or [],
        "loop_count": run.loop_count or 0,
        "error": run.error,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        # Bet 2.C — resume support
        "last_completed_node": getattr(run, "last_completed_node", None),
        "state_snapshot": getattr(run, "state_snapshot", None),
    }


async def create_or_reset_pipeline_run(
    chat_history_id: str,
    user_id: str,
    db: Session,
    *,
    preserve_snapshot: bool = False,
) -> dict:
    """
    Insert a new pipeline_runs row for the project, or reset an existing one
    back to status='queued' (used on retry after a failure). Always returns
    the run in queued state with empty stages_completed.

    `preserve_snapshot=True` keeps state_snapshot + last_completed_node so the
    /full-pipeline/resume endpoint can hand them to the runner.
    """
    try:
        run = (
            db.query(models.PipelineRun)
            .filter(models.PipelineRun.chat_history_id == chat_history_id)
            .first()
        )
        if run:
            run.status = models.PipelineRunStatus.QUEUED
            run.error = None
            run.completed_at = None
            if not preserve_snapshot:
                # Full restart — clear progress and snapshot.
                run.current_stage = None
                run.stages_completed = []
                run.loop_count = 0
                run.state_snapshot = None
                run.last_completed_node = None
                flag_modified(run, "stages_completed")
            # else (resume): preserve current_stage / stages_completed / loop_count
            # so the UI keeps showing completed steps. The runner re-streams the
            # graph and each already-completed node short-circuits via
            # completed_nodes; new mark_stage_* calls overwrite as needed.
        else:
            run = models.PipelineRun(
                run_id=new_id(),
                chat_history_id=chat_history_id,
                user_id=user_id,
                status=models.PipelineRunStatus.QUEUED,
                stages_completed=[],
                loop_count=0,
            )
            db.add(run)
        db.commit()
        db.refresh(run)
        return _serialize_pipeline_run(run)
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Failed to create/reset pipeline_run for {chat_history_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create pipeline run: {str(e)}",
        )


async def mark_stage_started(run_id: str, stage_name: str, db: Session) -> None:
    """Update pipeline_runs.current_stage and flip status to 'running'."""
    from datetime import datetime
    try:
        run = db.query(models.PipelineRun).filter(models.PipelineRun.run_id == run_id).first()
        if not run:
            logger.warning(f"mark_stage_started: run_id {run_id} not found")
            return
        run.current_stage = stage_name
        if run.status == models.PipelineRunStatus.QUEUED:
            run.status = models.PipelineRunStatus.RUNNING
            run.started_at = run.started_at or datetime.utcnow()
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"mark_stage_started failed for {run_id}/{stage_name}: {e}")


async def mark_stage_completed(run_id: str, stage_name: str, duration_ms: int, db: Session) -> None:
    """Append a completed-stage entry to stages_completed (JSON array)."""
    from datetime import datetime
    try:
        run = db.query(models.PipelineRun).filter(models.PipelineRun.run_id == run_id).first()
        if not run:
            logger.warning(f"mark_stage_completed: run_id {run_id} not found")
            return
        completed = list(run.stages_completed or [])
        completed.append({
            "stage": stage_name,
            "completed_at": datetime.utcnow().isoformat(),
            "duration_ms": int(duration_ms),
        })
        run.stages_completed = completed
        flag_modified(run, "stages_completed")
        # Clear current_stage if it matches the just-completed one
        if run.current_stage == stage_name:
            run.current_stage = None
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"mark_stage_completed failed for {run_id}/{stage_name}: {e}")


async def increment_loop_count(run_id: str, db: Session) -> None:
    """Bump loop_count when the critic loops back to solution_architect."""
    try:
        run = db.query(models.PipelineRun).filter(models.PipelineRun.run_id == run_id).first()
        if not run:
            return
        run.loop_count = (run.loop_count or 0) + 1
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"increment_loop_count failed for {run_id}: {e}")


async def complete_pipeline_run(run_id: str, db: Session) -> None:
    """Mark a pipeline run as successfully completed and freeze its COGS roll-up."""
    from datetime import datetime
    from sqlalchemy import func
    try:
        run = db.query(models.PipelineRun).filter(models.PipelineRun.run_id == run_id).first()
        if not run:
            return
        # Materialize the cost roll-up from the append-only ledger so billing reads
        # are O(1) and frozen at completion (immune to later price-table changes).
        total, count = (
            db.query(
                func.coalesce(func.sum(models.LLMCallLog.cost_usd), 0.0),
                func.count(models.LLMCallLog.id),
            )
            .filter(models.LLMCallLog.pipeline_run_id == run_id)
            .one()
        )
        run.total_cost_usd = float(total or 0.0)
        run.total_calls = int(count or 0)
        run.status = models.PipelineRunStatus.COMPLETED
        run.current_stage = None
        run.completed_at = datetime.utcnow()
        db.commit()
        logger.info(
            f"complete_pipeline_run {run_id}: {run.total_calls} LLM calls, "
            f"${run.total_cost_usd:.4f} COGS"
        )
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"complete_pipeline_run failed for {run_id}: {e}")


async def update_presales_cost_total(presales_id: str, db: Session) -> tuple[float, int]:
    """Materialize SUM/COUNT of llm_call_log onto presales_analysis for a project.

    Call after the initial scan saves, and again at the end of brief generation,
    so presales_analysis.total_cost_usd tracks the full project COGS (scan + brief
    + presales chat). The per-call detail stays in llm_call_log. Returns the
    (total_cost_usd, total_calls) it wrote.
    """
    from sqlalchemy import func
    try:
        total, count = (
            db.query(
                func.coalesce(func.sum(models.LLMCallLog.cost_usd), 0.0),
                func.count(models.LLMCallLog.id),
            )
            .filter(models.LLMCallLog.presales_id == presales_id)
            .one()
        )
        pre = (
            db.query(models.PresalesAnalysis)
            .filter(models.PresalesAnalysis.presales_id == presales_id)
            .first()
        )
        if pre:
            pre.total_cost_usd = float(total or 0.0)
            pre.total_calls = int(count or 0)
            db.commit()
        return float(total or 0.0), int(count or 0)
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"update_presales_cost_total failed for {presales_id}: {e}")
        return 0.0, 0


async def fail_pipeline_run(run_id: str, error_msg: str, db: Session) -> None:
    """Mark a pipeline run as failed and record the error message."""
    from datetime import datetime
    try:
        run = db.query(models.PipelineRun).filter(models.PipelineRun.run_id == run_id).first()
        if not run:
            return
        run.status = models.PipelineRunStatus.FAILED
        run.error = (error_msg or "Unknown error")[:4000]
        run.completed_at = datetime.utcnow()
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"fail_pipeline_run failed for {run_id}: {e}")


async def persist_state_snapshot(
    run_id: str,
    state_subset: dict,
    node_name: str,
    db: Session,
) -> None:
    """
    Bet 2.C — checkpoint the LangGraph state after a node completes.

    `state_subset` is a dict of state keys the runner wants to persist for
    resume. The current allowlist (set in pipeline_runner.run_full_pipeline_async)
    covers every downstream-consumed key: req_analysis, solution_archi,
    critic_report, evidence_report, feasibility_report, loop_count,
    current_loop_node, completed_nodes. Non-JSON values (LangChain BaseMessage
    objects, etc.) are coerced via `_coerce_state_for_snapshot`.

    On failure mid-pipeline this snapshot lets /full-pipeline/resume hydrate a
    fresh run with the work the previous run produced, so already-completed
    nodes short-circuit instead of re-calling the LLM.
    """
    try:
        run = db.query(models.PipelineRun).filter(models.PipelineRun.run_id == run_id).first()
        if not run:
            logger.warning(f"persist_state_snapshot: run_id {run_id} not found")
            return
        # Strip non-JSON-serializable values defensively. LangChain messages are
        # the usual offender (BaseMessage objects), so coerce them to plain dicts.
        try:
            json.dumps(state_subset)
            payload = state_subset
        except (TypeError, ValueError):
            payload = _coerce_state_for_snapshot(state_subset)
        run.state_snapshot = payload
        run.last_completed_node = node_name[:64] if node_name else None
        flag_modified(run, "state_snapshot")
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"persist_state_snapshot failed for {run_id}/{node_name}: {e}")


def _coerce_state_for_snapshot(state: dict) -> dict:
    """Best-effort JSON coercion of a LangGraph state dict for the snapshot column."""
    def _coerce(v):
        if v is None or isinstance(v, (str, int, float, bool)):
            return v
        if isinstance(v, list):
            return [_coerce(x) for x in v]
        if isinstance(v, dict):
            return {str(k): _coerce(x) for k, x in v.items()}
        # langchain Message objects expose .content; everything else falls back to str.
        content = getattr(v, "content", None)
        if content is not None:
            return {"type": v.__class__.__name__, "content": str(content)}
        return str(v)
    return {str(k): _coerce(v) for k, v in (state or {}).items()}


async def get_resumable_run(chat_history_id: str, db: Session):
    """
    Bet 2.C — return a failed run only if it has a checkpoint to resume from.

    Returns the serialized run or None. Callers use this to gate the
    /full-pipeline/resume endpoint (409 when not resumable).
    """
    try:
        run = (
            db.query(models.PipelineRun)
            .filter(models.PipelineRun.chat_history_id == chat_history_id)
            .filter(models.PipelineRun.status == models.PipelineRunStatus.FAILED)
            .filter(models.PipelineRun.last_completed_node.isnot(None))
            .first()
        )
        return _serialize_pipeline_run(run) if run else None
    except SQLAlchemyError as e:
        logger.error(f"get_resumable_run failed for {chat_history_id}: {e}")
        return None


async def get_pipeline_run_by_chat(chat_history_id: str, db: Session):
    """Return the serialized pipeline run for a project, or None if no row exists."""
    try:
        run = (
            db.query(models.PipelineRun)
            .filter(models.PipelineRun.chat_history_id == chat_history_id)
            .first()
        )
        return _serialize_pipeline_run(run) if run else None
    except SQLAlchemyError as e:
        logger.error(f"get_pipeline_run_by_chat failed for {chat_history_id}: {e}")
        return None


async def get_pipeline_status_map(chat_history_ids: list, db: Session) -> dict:
    """Bulk fetch pipeline_status keyed by chat_history_id for the projects overview."""
    if not chat_history_ids:
        return {}
    try:
        rows = (
            db.query(models.PipelineRun.chat_history_id, models.PipelineRun.status)
            .filter(models.PipelineRun.chat_history_id.in_(chat_history_ids))
            .all()
        )
        return {cid: status for cid, status in rows}
    except SQLAlchemyError as e:
        logger.error(f"get_pipeline_status_map failed: {e}")
        return {}


# ============================================================================
# FIRM CONTEXT (Bet 3, migration 019)
# ============================================================================

def _serialize_firm(firm) -> dict:
    return {
        "firm_id": firm.firm_id,
        "name": firm.name,
        "logo_url": firm.logo_url,
        "primary_color": firm.primary_color,
        "created_at": firm.created_at.isoformat() if firm.created_at else None,
    }


def _serialize_rate_card(r) -> dict:
    return {
        "rate_id": r.rate_id,
        "firm_id": r.firm_id,
        "role": r.role,
        "seniority": r.seniority,
        "region": r.region,
        "hourly_rate_usd": float(r.hourly_rate_usd) if r.hourly_rate_usd is not None else None,
        "version": r.version,
        "active": r.active,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _serialize_team_template(t) -> dict:
    return {
        "template_id": t.template_id,
        "firm_id": t.firm_id,
        "template_name": t.template_name,
        "engagement_type": t.engagement_type,
        "roles": t.roles or [],
        "notes": t.notes,
        "active": t.active,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


def _serialize_tech_pref(p) -> dict:
    return {
        "pref_id": p.pref_id,
        "firm_id": p.firm_id,
        "category": p.category,
        "preferred": p.preferred or [],
        "anti_preferred": p.anti_preferred or [],
        "rationale": p.rationale,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


def _serialize_past_project(p) -> dict:
    return {
        "project_id": p.project_id,
        "firm_id": p.firm_id,
        "project_name": p.project_name,
        "client_name": p.client_name,
        "engagement_type": p.engagement_type,
        "start_date": p.start_date.isoformat() if p.start_date else None,
        "end_date": p.end_date.isoformat() if p.end_date else None,
        "summary": p.summary,
        "original_brief_md": p.original_brief_md,
        "final_report_md": p.final_report_md,
        "retrospective_md": p.retrospective_md,
        "effort_estimated_weeks": float(p.effort_estimated_weeks) if p.effort_estimated_weeks is not None else None,
        "effort_actual_weeks": float(p.effort_actual_weeks) if p.effort_actual_weeks is not None else None,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


# ---- Firm membership ----

def get_firm_for_user(user_id: str, db: Session) -> Optional[dict]:
    """Returns the firm row + the user's firm_role, or None if user has no firm yet."""
    try:
        u = db.query(models.User).filter(models.User.user_id == user_id).first()
        if not u or not u.firm_id:
            return None
        firm = db.query(models.Firm).filter(models.Firm.firm_id == u.firm_id).first()
        if not firm:
            return None
        return {**_serialize_firm(firm), "firm_role": u.firm_role}
    except SQLAlchemyError as e:
        logger.error(f"get_firm_for_user failed for {user_id}: {e}")
        return None


def ensure_firm_for_new_user(user_id: str, db: Session) -> Optional[str]:
    """
    Idempotently ensure the user has a firm. If not, create a 1-person firm named
    after the user and assign firm_admin. Returns the firm_id.

    Called from signup flows so every new user can immediately use the admin UI.
    """
    try:
        u = db.query(models.User).filter(models.User.user_id == user_id).first()
        if not u:
            return None
        if u.firm_id:
            return u.firm_id

        firm_name = (u.full_name or u.email_address or "My firm").strip()
        if not firm_name.endswith("firm") and not firm_name.endswith("Firm"):
            firm_name = f"{firm_name}'s firm"

        firm = models.Firm(name=firm_name)
        db.add(firm)
        db.flush()  # populate firm.firm_id

        u.firm_id = firm.firm_id
        u.firm_role = "firm_admin"
        db.commit()
        db.refresh(u)
        return u.firm_id
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"ensure_firm_for_new_user failed for {user_id}: {e}")
        return None


def update_firm(firm_id: str, updates: dict, db: Session) -> Optional[dict]:
    try:
        firm = db.query(models.Firm).filter(models.Firm.firm_id == firm_id).first()
        if not firm:
            return None
        for k in ("name", "logo_url", "primary_color"):
            if k in updates and updates[k] is not None:
                setattr(firm, k, updates[k])
        db.commit()
        db.refresh(firm)
        return _serialize_firm(firm)
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"update_firm failed for {firm_id}: {e}")
        return None


# ---- Rate cards ----

def list_rate_cards(firm_id: str, db: Session, active_only: bool = True) -> list:
    q = db.query(models.FirmRateCard).filter(models.FirmRateCard.firm_id == firm_id)
    if active_only:
        q = q.filter(models.FirmRateCard.active == True)  # noqa: E712
    return [_serialize_rate_card(r) for r in q.order_by(models.FirmRateCard.role, models.FirmRateCard.seniority).all()]


def create_rate_card(firm_id: str, data: dict, db: Session) -> dict:
    try:
        row = models.FirmRateCard(
            firm_id=firm_id,
            role=data["role"],
            seniority=data["seniority"],
            region=data["region"],
            hourly_rate_usd=data["hourly_rate_usd"],
            version=data.get("version", 1),
            active=data.get("active", True),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return _serialize_rate_card(row)
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"create_rate_card failed: {e}")


def update_rate_card(firm_id: str, rate_id: str, updates: dict, db: Session) -> Optional[dict]:
    try:
        row = (
            db.query(models.FirmRateCard)
            .filter(models.FirmRateCard.firm_id == firm_id,
                    models.FirmRateCard.rate_id == rate_id)
            .first()
        )
        if not row:
            return None
        for k in ("role", "seniority", "region", "hourly_rate_usd", "version", "active"):
            if k in updates and updates[k] is not None:
                setattr(row, k, updates[k])
        db.commit()
        db.refresh(row)
        return _serialize_rate_card(row)
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"update_rate_card failed: {e}")


def delete_rate_card(firm_id: str, rate_id: str, db: Session) -> bool:
    try:
        row = (
            db.query(models.FirmRateCard)
            .filter(models.FirmRateCard.firm_id == firm_id,
                    models.FirmRateCard.rate_id == rate_id)
            .first()
        )
        if not row:
            return False
        db.delete(row)
        db.commit()
        return True
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"delete_rate_card failed: {e}")


# ---- Team templates ----

def list_team_templates(firm_id: str, db: Session, active_only: bool = True) -> list:
    q = db.query(models.FirmTeamTemplate).filter(models.FirmTeamTemplate.firm_id == firm_id)
    if active_only:
        q = q.filter(models.FirmTeamTemplate.active == True)  # noqa: E712
    return [_serialize_team_template(t) for t in q.order_by(models.FirmTeamTemplate.template_name).all()]


def get_team_template_for_engagement(firm_id: str, engagement_type: Optional[str], db: Session) -> Optional[dict]:
    if not engagement_type:
        return None
    row = (
        db.query(models.FirmTeamTemplate)
        .filter(models.FirmTeamTemplate.firm_id == firm_id,
                models.FirmTeamTemplate.engagement_type == engagement_type,
                models.FirmTeamTemplate.active == True)  # noqa: E712
        .first()
    )
    return _serialize_team_template(row) if row else None


def create_team_template(firm_id: str, data: dict, db: Session) -> dict:
    try:
        row = models.FirmTeamTemplate(
            firm_id=firm_id,
            template_name=data["template_name"],
            engagement_type=data.get("engagement_type"),
            roles=data.get("roles", []),
            notes=data.get("notes"),
            active=data.get("active", True),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return _serialize_team_template(row)
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"create_team_template failed: {e}")


def update_team_template(firm_id: str, template_id: str, updates: dict, db: Session) -> Optional[dict]:
    try:
        row = (
            db.query(models.FirmTeamTemplate)
            .filter(models.FirmTeamTemplate.firm_id == firm_id,
                    models.FirmTeamTemplate.template_id == template_id)
            .first()
        )
        if not row:
            return None
        for k in ("template_name", "engagement_type", "roles", "notes", "active"):
            if k in updates and updates[k] is not None:
                setattr(row, k, updates[k])
        if "roles" in updates:
            flag_modified(row, "roles")
        db.commit()
        db.refresh(row)
        return _serialize_team_template(row)
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"update_team_template failed: {e}")


def delete_team_template(firm_id: str, template_id: str, db: Session) -> bool:
    try:
        row = (
            db.query(models.FirmTeamTemplate)
            .filter(models.FirmTeamTemplate.firm_id == firm_id,
                    models.FirmTeamTemplate.template_id == template_id)
            .first()
        )
        if not row:
            return False
        db.delete(row)
        db.commit()
        return True
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"delete_team_template failed: {e}")


# ---- Tech preferences ----

def list_tech_preferences(firm_id: str, db: Session) -> list:
    rows = (
        db.query(models.FirmTechPreference)
        .filter(models.FirmTechPreference.firm_id == firm_id)
        .order_by(models.FirmTechPreference.category)
        .all()
    )
    return [_serialize_tech_pref(p) for p in rows]


def create_tech_preference(firm_id: str, data: dict, db: Session) -> dict:
    try:
        row = models.FirmTechPreference(
            firm_id=firm_id,
            category=data["category"],
            preferred=data.get("preferred", []),
            anti_preferred=data.get("anti_preferred", []),
            rationale=data.get("rationale"),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return _serialize_tech_pref(row)
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"create_tech_preference failed: {e}")


def update_tech_preference(firm_id: str, pref_id: str, updates: dict, db: Session) -> Optional[dict]:
    try:
        row = (
            db.query(models.FirmTechPreference)
            .filter(models.FirmTechPreference.firm_id == firm_id,
                    models.FirmTechPreference.pref_id == pref_id)
            .first()
        )
        if not row:
            return None
        for k in ("category", "preferred", "anti_preferred", "rationale"):
            if k in updates and updates[k] is not None:
                setattr(row, k, updates[k])
        for jcol in ("preferred", "anti_preferred"):
            if jcol in updates:
                flag_modified(row, jcol)
        db.commit()
        db.refresh(row)
        return _serialize_tech_pref(row)
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"update_tech_preference failed: {e}")


def delete_tech_preference(firm_id: str, pref_id: str, db: Session) -> bool:
    try:
        row = (
            db.query(models.FirmTechPreference)
            .filter(models.FirmTechPreference.firm_id == firm_id,
                    models.FirmTechPreference.pref_id == pref_id)
            .first()
        )
        if not row:
            return False
        db.delete(row)
        db.commit()
        return True
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"delete_tech_preference failed: {e}")


# ---- Past projects ----

def list_past_projects(firm_id: str, db: Session) -> list:
    rows = (
        db.query(models.FirmPastProject)
        .filter(models.FirmPastProject.firm_id == firm_id)
        .order_by(models.FirmPastProject.created_at.desc())
        .all()
    )
    return [_serialize_past_project(p) for p in rows]


def get_past_project(firm_id: str, project_id: str, db: Session) -> Optional[dict]:
    row = (
        db.query(models.FirmPastProject)
        .filter(models.FirmPastProject.firm_id == firm_id,
                models.FirmPastProject.project_id == project_id)
        .first()
    )
    return _serialize_past_project(row) if row else None


def create_past_project(firm_id: str, data: dict, db: Session) -> dict:
    try:
        row = models.FirmPastProject(
            firm_id=firm_id,
            project_name=data["project_name"],
            client_name=data.get("client_name"),
            engagement_type=data.get("engagement_type"),
            start_date=data.get("start_date"),
            end_date=data.get("end_date"),
            summary=data.get("summary"),
            original_brief_md=data.get("original_brief_md"),
            final_report_md=data.get("final_report_md"),
            retrospective_md=data.get("retrospective_md"),
            effort_estimated_weeks=data.get("effort_estimated_weeks"),
            effort_actual_weeks=data.get("effort_actual_weeks"),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return _serialize_past_project(row)
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"create_past_project failed: {e}")


def update_past_project(firm_id: str, project_id: str, updates: dict, db: Session) -> Optional[dict]:
    try:
        row = (
            db.query(models.FirmPastProject)
            .filter(models.FirmPastProject.firm_id == firm_id,
                    models.FirmPastProject.project_id == project_id)
            .first()
        )
        if not row:
            return None
        for k in (
            "project_name", "client_name", "engagement_type", "start_date", "end_date",
            "summary", "original_brief_md", "final_report_md", "retrospective_md",
            "effort_estimated_weeks", "effort_actual_weeks",
        ):
            if k in updates and updates[k] is not None:
                setattr(row, k, updates[k])
        db.commit()
        db.refresh(row)
        return _serialize_past_project(row)
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"update_past_project failed: {e}")


def delete_past_project(firm_id: str, project_id: str, db: Session) -> bool:
    try:
        row = (
            db.query(models.FirmPastProject)
            .filter(models.FirmPastProject.firm_id == firm_id,
                    models.FirmPastProject.project_id == project_id)
            .first()
        )
        if not row:
            return False
        db.delete(row)
        db.commit()
        return True
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"delete_past_project failed: {e}")


# ---------------------------------------------------------------------------
# Jira credentials — server-side OAuth token storage (one row per user).
# ---------------------------------------------------------------------------
def get_jira_credentials(user_id: str, db: Session):
    """Return the user's JiraCredential row, or None if Jira isn't connected."""
    return db.query(models.JiraCredential).filter(models.JiraCredential.user_id == user_id).first()


def save_jira_credentials(user_id: str, *, access_token: str, refresh_token: Optional[str] = None,
                          cloud_id: Optional[str] = None, account_id: Optional[str] = None,
                          email: Optional[str] = None, scope: Optional[str] = None,
                          expires_at: Optional[datetime] = None, db: Session) -> dict:
    """Upsert a user's Jira tokens. Used by the OAuth callback (full set) and the
    refresh path (new access token + rotated refresh + expiry)."""
    try:
        from utils.crypto import encrypt_secret
        row = db.query(models.JiraCredential).filter(models.JiraCredential.user_id == user_id).first()
        if row is None:
            row = models.JiraCredential(user_id=user_id)
            db.add(row)
        # Encrypt the secret tokens at rest (Fernet). email/account_id/scope are not secrets.
        row.access_token = encrypt_secret(access_token)
        if refresh_token is not None:
            row.refresh_token = encrypt_secret(refresh_token)
        if cloud_id is not None:
            row.cloud_id = cloud_id
        if account_id is not None:
            row.account_id = account_id
        if email is not None:
            row.email = email
        if scope is not None:
            row.scope = scope
        row.expires_at = expires_at
        db.commit()
        db.refresh(row)
        return {"user_id": user_id, "connected": True}
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"save_jira_credentials failed: {e}")


def delete_jira_credentials(user_id: str, db: Session) -> bool:
    """Disconnect Jira for a user. Idempotent."""
    try:
        row = db.query(models.JiraCredential).filter(models.JiraCredential.user_id == user_id).first()
        if not row:
            return False
        db.delete(row)
        db.commit()
        return True
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"delete_jira_credentials failed: {e}")
