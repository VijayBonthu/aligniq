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
            provider = provider
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
                "created_at": record.created_at.isoformat() if record.created_at else None,
                "summary": record.summary_report.get("executive_summary", "No summary available") if record.summary_report else "No summary",
                "is_latest": record.version_number == records[0].version_number if records else False
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
            "created_at": record.created_at.isoformat() if record.created_at else None
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
    db: Session
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

    Returns:
        Dict with new version details
    """
    try:
        # Get the latest version number
        latest = db.query(models.ReportVersions).filter(
            models.ReportVersions.chat_history_id == chat_history_id
        ).order_by(models.ReportVersions.version_number.desc()).first()

        new_version_number = (latest.version_number + 1) if latest else 1

        # Create new version record
        new_version = models.ReportVersions(
            report_version_id=str(uuid.uuid4()),
            chat_history_id=chat_history_id,
            user_id=user_id,
            version_number=new_version_number,
            report_content=report_content,
            summary_report=summary_report,
            pending_changes=[]  # Clear pending changes for new version
        )

        db.add(new_version)
        db.commit()
        db.refresh(new_version)

        logger.info(f"Created new report version {new_version_number} for chat_history_id: {chat_history_id}")

        return {
            "status": "success",
            "report_version_id": new_version.report_version_id,
            "version_number": new_version_number,
            "changes_applied": len(changes_applied),
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
            "original_version": target_version_number
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
    db: Session
) -> dict:
    """
    Create a link between document and presales analysis.

    This allows tracking the journey from pre-sales scan to full report.

    Args:
        document_id: The document ID
        user_id: The user ID
        presales_id: The presales analysis ID
        db: Database session

    Returns:
        Dict with link_id
    """
    try:
        link = models.AnalysisLink(
            document_id=document_id,
            user_id=user_id,
            presales_id=presales_id
        )

        db.add(link)
        db.commit()
        db.refresh(link)

        logger.info(f"Created analysis link: {link.link_id} for document: {document_id}")

        return {"link_id": link.link_id}

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



