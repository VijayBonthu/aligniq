from fastapi import Depends, APIRouter, HTTPException, Request, Header, Body, UploadFile, File, Form
from fastapi.responses import FileResponse
from utils.token_generation import token_validator
from sqlalchemy.orm import Session
from models import get_db
from utils.integrations import Integrations
from jira_logic.jira_components import get_valid_jira_access_token
from database_scripts import get_jira_credentials, delete_jira_credentials
from utils.logger import logger
import os
import json

router = APIRouter()


# ============================================================
# Jira client builder — tokens live server-side (jira_credentials),
# refreshed in place. No Jira token is ever sent from the browser.
# ============================================================
async def _integ(current_user, db: Session) -> Integrations:
    """Build a Jira client for the current app user from their stored, auto-refreshed
    Atlassian token. Raises 401 if Jira isn't connected (→ UI prompts reconnect)."""
    user_id = current_user["regular_login_token"]["id"]
    access_token = await get_valid_jira_access_token(user_id, db)
    return Integrations(access_token)


@router.get("/jira/status")
async def jira_status(current_user=Depends(token_validator), db: Session = Depends(get_db)):
    """Whether the current user has Jira connected (server-side truth). The SPA polls
    this after the OAuth popup and to render Connected / Disconnect state."""
    user_id = current_user["regular_login_token"]["id"]
    cred = get_jira_credentials(user_id, db)
    return {
        "connected": bool(cred),
        "email": cred.email if cred else None,
        "account_id": cred.account_id if cred else None,
    }


@router.post("/jira/disconnect")
async def jira_disconnect(current_user=Depends(token_validator), db: Session = Depends(get_db)):
    """Disconnect Jira for the current user (deletes the stored tokens)."""
    user_id = current_user["regular_login_token"]["id"]
    delete_jira_credentials(user_id, db)
    return {"connected": False}


@router.get("/jira/get_issues")
async def get_jira_issues(current_user=Depends(token_validator), db: Session = Depends(get_db)):
    integ = await _integ(current_user, db)
    return {"issues": integ.get_all_issues()}


@router.get("/jira/download_attachments")
async def download_jira_attachements(
    issue_key: str = None, download_file_name: str = None, attachment_id=None,
    current_user=Depends(token_validator), db: Session = Depends(get_db),
):
    if not issue_key:
        raise HTTPException(status_code=400, detail="issue key is required")
    if not download_file_name:
        raise HTTPException(status_code=400, detail="download file name is required")
    if not attachment_id:
        raise HTTPException(status_code=400, detail="attachment id is required")
    integ = await _integ(current_user, db)
    issues = integ.download_jira_attachments(
        issue_key=issue_key, download_file_name=download_file_name, attachment_id=attachment_id
    )
    if not issues or len(issues) == 0:
        raise HTTPException(status_code=404, detail="Attachment not found")

    file_info = issues[0]
    file_path = file_info['local_path']
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Attachment file not found")
    content_type = "application/octet-stream"
    if download_file_name.lower().endswith('.pdf'):
        content_type = "application/pdf"
    elif download_file_name.lower().endswith('.docx'):
        content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    elif download_file_name.lower().endswith('.doc'):
        content_type = "application/msword"
    elif download_file_name.lower().endswith('.txt'):
        content_type = "text/plain"
    return FileResponse(path=file_path, filename=download_file_name, media_type=content_type)


@router.get('/jira/get_single_issue/{issue_key}')
async def get_single_issue(issue_key: str = None, current_user=Depends(token_validator), db: Session = Depends(get_db)):
    if not issue_key:
        raise HTTPException(status_code=400, detail="issue key is required")
    integ = await _integ(current_user, db)
    return {"issues": integ.get_single_issues_(issue_key=issue_key)}


# ============================================================
# WRITE side — report -> Jira delivery handoff + ticket management
# ============================================================

@router.get("/jira/projects")
async def list_jira_projects(current_user=Depends(token_validator), db: Session = Depends(get_db)):
    """List Jira projects the user can push report items into (key + name)."""
    integ = await _integ(current_user, db)
    return {"projects": integ.get_projects()}


@router.get("/jira/epics")
async def list_jira_epics(project_key: str, current_user=Depends(token_validator), db: Session = Depends(get_db)):
    """Epics in a project, for the 'attach stories to existing epic' picker."""
    if not project_key:
        raise HTTPException(status_code=400, detail="project_key is required")
    integ = await _integ(current_user, db)
    return {"epics": integ.list_epics(project_key)}


@router.get("/jira/issues/search")
async def search_jira_issues(project_key: str, current_user=Depends(token_validator), db: Session = Depends(get_db)):
    """Browse issues in a project (most-recently-updated first) for the manage tab."""
    if not project_key:
        raise HTTPException(status_code=400, detail="project_key is required")
    integ = await _integ(current_user, db)
    return {"issues": integ.search_issues(project_key)}


@router.get("/jira/issue/{issue_key}/children")
async def list_jira_children(issue_key: str, current_user=Depends(token_validator), db: Session = Depends(get_db)):
    """Child issues (stories/tasks/sub-tasks) under an epic/story — powers the
    epic -> children drill-down so the user attaches at the right level."""
    integ = await _integ(current_user, db)
    return {"issues": integ.list_children(issue_key)}


@router.get("/jira/report-items")
async def jira_report_items(
    chat_history_id: str,
    scope: str = "risks",
    current_user=Depends(token_validator),
    db: Session = Depends(get_db),
):
    """Preview the items a push would create — derives from the report WITHOUT touching
    Jira. Powers the editable builder so the user selects/edits before anything is created.
    (No Jira connection needed; it's purely report-derived.)"""
    if not chat_history_id:
        raise HTTPException(status_code=400, detail="chat_history_id is required")

    from database_scripts import get_summary_report
    from utils.report_sections import report_delivery_items

    report = await get_summary_report(chat_history_id, db)
    if not report or not getattr(report, "report_content", None):
        raise HTTPException(status_code=404, detail="No report found for this chat")

    summary = report.summary_report if isinstance(getattr(report, "summary_report", None), dict) else {}
    markdown = report.report_content if isinstance(report.report_content, str) else ""
    exec_summary, items = report_delivery_items(markdown, summary, scope=scope)
    # synthesize stable ids for UI keying/selection (items carry only summary+description)
    items = [{"id": f"item-{i}", "summary": it["summary"], "description": it["description"]}
             for i, it in enumerate(items)]
    return {"exec_summary": exec_summary, "items": items, "scope": scope}


@router.put("/jira/issue/{issue_key}")
async def update_jira_issue(issue_key: str, payload: dict = Body(...),
                            current_user=Depends(token_validator), db: Session = Depends(get_db)):
    """Edit an existing issue's summary and/or description."""
    integ = await _integ(current_user, db)
    return integ.update_issue(
        issue_key,
        summary=(payload or {}).get("summary"),
        description=(payload or {}).get("description"),
    )


@router.post("/jira/issue/{issue_key}/labels")
async def set_jira_labels(issue_key: str, payload: dict = Body(...),
                          current_user=Depends(token_validator), db: Session = Depends(get_db)):
    """Add and/or remove labels (tags) on an issue."""
    integ = await _integ(current_user, db)
    return integ.set_labels(
        issue_key,
        add=(payload or {}).get("add") or [],
        remove=(payload or {}).get("remove") or [],
    )


@router.post("/jira/issue/{issue_key}/comment")
async def comment_jira_issue(issue_key: str, payload: dict = Body(...),
                             current_user=Depends(token_validator), db: Session = Depends(get_db)):
    """Post a comment on an issue."""
    body = (payload or {}).get("body")
    if not body or not str(body).strip():
        raise HTTPException(status_code=400, detail="Comment body is required")
    integ = await _integ(current_user, db)
    return integ.add_comment(issue_key, str(body))


@router.get("/jira/issue/{issue_key}/transitions")
async def jira_issue_transitions(issue_key: str, current_user=Depends(token_validator), db: Session = Depends(get_db)):
    """Available workflow transitions for an issue (To Do -> In Progress -> Done)."""
    integ = await _integ(current_user, db)
    return {"transitions": integ.get_transitions(issue_key)}


@router.post("/jira/issue/{issue_key}/transition")
async def transition_jira_issue(issue_key: str, payload: dict = Body(...),
                                current_user=Depends(token_validator), db: Session = Depends(get_db)):
    """Move an issue across its workflow by transition id."""
    transition_id = (payload or {}).get("transition_id")
    if not transition_id:
        raise HTTPException(status_code=400, detail="transition_id is required")
    integ = await _integ(current_user, db)
    return integ.transition_issue(issue_key, transition_id)


@router.post("/jira/issue")
async def create_single_jira_issue(payload: dict = Body(...),
                                   current_user=Depends(token_validator), db: Session = Depends(get_db)):
    """Create a single issue/epic (the 'new target' for a deliverable push)."""
    project_key = (payload or {}).get("project_key")
    summary = (payload or {}).get("summary")
    if not project_key or not summary:
        raise HTTPException(status_code=400, detail="project_key and summary are required")
    issue_type = (payload or {}).get("issue_type") or "Task"
    description = (payload or {}).get("description") or ""
    parent_key = (payload or {}).get("parent_key")  # e.g. create a Story under an Epic
    integ = await _integ(current_user, db)
    if issue_type.lower() == "epic":
        created = integ.create_epic(project_key, summary, description, labels=["groundediq"])
    else:
        created = integ.create_issue(project_key, summary, description, issue_type=issue_type,
                                     parent_key=parent_key, labels=["groundediq"])
    return {"key": created.get("key"), "browse_url": created.get("browse_url")}


@router.get("/jira/users/search")
async def search_jira_users(project_key: str = None, query: str = "",
                            current_user=Depends(token_validator), db: Session = Depends(get_db)):
    """Search users assignable in a project — for the assign / @mention picker."""
    integ = await _integ(current_user, db)
    return {"users": integ.search_users(query=query, project_key=project_key)}


@router.post("/jira/issue/{issue_key}/attach")
async def attach_to_jira_issue(
    issue_key: str,
    file: UploadFile = File(...),
    comment: str = Form(None),
    assignee_id: str = Form(None),
    mention_ids: str = Form(None),  # JSON: [{account_id, display_name}]
    current_user=Depends(token_validator),
    db: Session = Depends(get_db),
):
    """Attach a file (the deliverable DOCX/PDF) to an issue, and optionally assign + comment
    (@mentioning teammates) in the same action — the Deliverable Builder's 'Send to Jira'."""
    integ = await _integ(current_user, db)
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")
    attachment = integ.add_attachment(issue_key, content, file.filename, file.content_type)
    if assignee_id:
        integ.assign_issue(issue_key, assignee_id)
    if comment and comment.strip():
        mentions = []
        if mention_ids:
            try:
                mentions = json.loads(mention_ids) or []
            except (ValueError, TypeError):
                mentions = []
        integ.add_comment(issue_key, comment.strip(), mentions=mentions)
    return {"key": issue_key, "browse_url": integ._browse_url(issue_key), "attachment": attachment}


@router.post("/jira/create-from-report")
async def create_jira_from_report(
    payload: dict = Body(...),
    current_user=Depends(token_validator),
    db: Session = Depends(get_db),
):
    """
    Create a Jira epic + child stories from a report's risks or sections — the
    report->delivery handoff.

    Body: {
      chat_history_id, project_key,
      scope: 'risks'|'sections', section_ids?: [],   # used when `items` is absent
      items?: [{ summary, description }],             # edited override from the builder
      epic_key?: str,                                 # attach to an existing epic instead of creating one
      labels?: [str]
    }
    Returns: { epic_key, epic, issue_keys, issues, scope, project_key }
    """
    integ = await _integ(current_user, db)

    chat_history_id = (payload or {}).get("chat_history_id")
    project_key = (payload or {}).get("project_key")
    scope = (payload or {}).get("scope", "risks")
    epic_key_in = (payload or {}).get("epic_key")
    override_items = (payload or {}).get("items")
    extra_labels = (payload or {}).get("labels") or []
    if not chat_history_id or not project_key:
        raise HTTPException(status_code=400, detail="chat_history_id and project_key are required")

    from database_scripts import get_summary_report
    from utils.report_sections import report_delivery_items

    report = await get_summary_report(chat_history_id, db)
    if not report or not getattr(report, "report_content", None):
        raise HTTPException(status_code=404, detail="No report found for this chat")

    summary = report.summary_report if isinstance(getattr(report, "summary_report", None), dict) else {}
    project_title = summary.get("project_summary") or summary.get("title") or "GroundedIQ Project"
    markdown = report.report_content if isinstance(report.report_content, str) else ""

    # Items: use the user-edited override verbatim when present, else derive from the report.
    if isinstance(override_items, list) and override_items:
        items = [{"summary": (it or {}).get("summary") or "Untitled",
                  "description": (it or {}).get("description") or ""}
                 for it in override_items if (it or {}).get("summary")]
        exec_summary = "Delivery work breakdown selected from the GroundedIQ analysis report."
    else:
        section_ids = set((payload or {}).get("section_ids") or [])
        exec_summary, items = report_delivery_items(markdown, summary, scope=scope, section_ids=section_ids)
    if not items:
        raise HTTPException(status_code=400, detail=f"Nothing to push for scope '{scope}'.")

    labels = ["groundediq"] + [l for l in extra_labels if l and l != "groundediq"]

    # Epic: attach to an existing one, or create a fresh epic for this push.
    if epic_key_in:
        epic_key = epic_key_in
        epic = {"key": epic_key, "browse_url": integ._browse_url(epic_key)}
    else:
        epic = integ.create_epic(project_key, f"{project_title} — GroundedIQ"[:250], exec_summary, labels=labels)
        epic_key = epic.get("key")

    issues = []
    for it in items[:50]:  # cap to avoid runaway creation
        created = integ.create_issue(
            project_key, it["summary"], it["description"],
            issue_type="Task", parent_key=epic_key, labels=labels,
        )
        if created.get("key"):
            issues.append({"key": created["key"], "browse_url": created.get("browse_url")})

    issue_keys = [i["key"] for i in issues]
    logger.info(f"Jira export: epic {epic_key} + {len(issue_keys)} stories for chat {chat_history_id}")
    return {
        "epic_key": epic_key, "epic": epic,
        "issue_keys": issue_keys, "issues": issues,
        "scope": scope, "project_key": project_key,
    }
