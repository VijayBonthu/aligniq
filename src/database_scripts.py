import models
from models import get_db
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from p_model_type import Registration_login
from sqlalchemy import and_
from utils.token_generation import hash_passwords
from fastapi import HTTPException, status
from utils.logger import logger
import copy
import uuid

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
        user_details = models.User(
            oauth_id = user_data["id"],
            email_address = user_data["email"],
            first_name = user_data["given_name"],
            last_name = user_data["family_name"],
            verified_email = user_data["verified_email"],
            full_name = user_data["name"],
            picture = user_data["picture"],
            provider = provider,
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
        record = query.filter(and_(
            models.User.provider=="Local", models.User.verified_email == "False", models.User.email_address == email_address
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
    try:
        query = db.query(models.ReportVersions).filter(models.ReportVersions.chat_history_id == chat_history_id).order_by(models.ReportVersions.created_at.desc())
        record = query.first()
        return record
    except SQLAlchemyError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error occured with the DB, chat history id: {chat_history_id}, error: {str(e)}")


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
            versions.append({
                "report_version_id": record.report_version_id,
                "version_number": record.version_number,
                "version": record.version_number,  # Alias for compatibility
                "created_at": record.created_at.isoformat() if record.created_at else None,
                "summary": record.summary_report.get("executive_summary", "No summary available") if record.summary_report else "No summary",
                "is_latest": record.version_number == records[0].version_number if records else False,
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
            "created_at": record.created_at.isoformat() if record.created_at else None,
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
    parent_version_id: str = None
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

        # Set all existing versions to is_default=False before creating new version
        # This ensures only the new version will have is_default=True
        db.query(models.ReportVersions).filter(
            models.ReportVersions.chat_history_id == chat_history_id
        ).update({"is_default": False})

        # Create new version record with changelog tracking
        new_version = models.ReportVersions(
            report_version_id=str(uuid.uuid4()),
            chat_history_id=chat_history_id,
            user_id=user_id,
            version_number=new_version_number,
            report_content=report_content,
            summary_report=summary_report,
            pending_changes=[],  # Clear pending changes for new version
            changes_applied=changes_applied,  # Store the changes that created this version
            changelog_summary=changelog_summary,  # Store the changelog summary
            parent_version_id=parent_version_id  # Track version lineage
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
            report_version_id=str(uuid.uuid4()),
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
        presales = models.PresalesAnalysis(
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
            "created_at": presales.created_at.isoformat() if presales.created_at else None
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
            id=str(uuid.uuid4()),
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
