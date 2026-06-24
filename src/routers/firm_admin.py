"""
Firm admin router (Bet 3). Mounted at /api/v1/firm.

All firm-scoped queries derive firm_id from the JWT (`current_token["regular_login_token"]["firm_id"]`)
via the helpers in `utils.auth_deps`. The request body never decides which firm
is being mutated — that's tenant isolation by construction.
"""
from __future__ import annotations

import csv
import io
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import database_scripts as db_scripts
from models import get_db
from utils.auth_deps import get_current_firm_id, get_current_user_payload, require_firm_admin
from utils.logger import logger
from vectordb.firm_projects import (
    delete_past_project_embeddings,
    embed_past_project,
)


router = APIRouter()


# ============================================================================
# Pydantic request bodies
# ============================================================================

class FirmUpdateBody(BaseModel):
    name: Optional[str] = None
    logo_url: Optional[str] = None
    primary_color: Optional[str] = None


class RateCardCreateBody(BaseModel):
    role: str
    seniority: str
    region: str
    hourly_rate_usd: float
    version: int = 1
    active: bool = True


class RateCardUpdateBody(BaseModel):
    role: Optional[str] = None
    seniority: Optional[str] = None
    region: Optional[str] = None
    hourly_rate_usd: Optional[float] = None
    version: Optional[int] = None
    active: Optional[bool] = None


class TeamTemplateCreateBody(BaseModel):
    template_name: str
    engagement_type: Optional[str] = None
    roles: list = Field(default_factory=list)
    notes: Optional[str] = None
    active: bool = True


class TeamTemplateUpdateBody(BaseModel):
    template_name: Optional[str] = None
    engagement_type: Optional[str] = None
    roles: Optional[list] = None
    notes: Optional[str] = None
    active: Optional[bool] = None


class TechPrefCreateBody(BaseModel):
    category: str
    preferred: list = Field(default_factory=list)
    anti_preferred: list = Field(default_factory=list)
    rationale: Optional[str] = None


class TechPrefUpdateBody(BaseModel):
    category: Optional[str] = None
    preferred: Optional[list] = None
    anti_preferred: Optional[list] = None
    rationale: Optional[str] = None


class PastProjectCreateBody(BaseModel):
    project_name: str
    client_name: Optional[str] = None
    engagement_type: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    summary: Optional[str] = None
    original_brief_md: Optional[str] = None
    final_report_md: Optional[str] = None
    retrospective_md: Optional[str] = None
    effort_estimated_weeks: Optional[float] = None
    effort_actual_weeks: Optional[float] = None


class PastProjectUpdateBody(BaseModel):
    project_name: Optional[str] = None
    client_name: Optional[str] = None
    engagement_type: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    summary: Optional[str] = None
    original_brief_md: Optional[str] = None
    final_report_md: Optional[str] = None
    retrospective_md: Optional[str] = None
    effort_estimated_weeks: Optional[float] = None
    effort_actual_weeks: Optional[float] = None


# ============================================================================
# Firm — current user's firm + role (any authed user)
# ============================================================================

@router.get("/firm/me")
async def get_my_firm(
    payload: dict = Depends(get_current_user_payload),
    db: Session = Depends(get_db),
):
    """Returns the requesting user's firm + role. Used by the frontend to
    show/hide the admin UI."""
    user_id = payload.get("id")
    if not user_id:
        raise HTTPException(status_code=400, detail="Missing user id in token")

    # On a fresh login the JWT already has firm_id/firm_role, but we also
    # double-check the DB in case the user was created before migration 019
    # ran and never logged out/in afterwards. ensure_firm_for_new_user is
    # idempotent.
    firm_id = payload.get("firm_id")
    if not firm_id:
        firm_id = db_scripts.ensure_firm_for_new_user(user_id, db)
        if not firm_id:
            raise HTTPException(status_code=500, detail="Could not assign firm to user")

    firm = db_scripts.get_firm_for_user(user_id, db)
    if not firm:
        raise HTTPException(status_code=404, detail="Firm not found")
    return firm


@router.patch("/firm/me")
async def patch_my_firm(
    body: FirmUpdateBody,
    payload: dict = Depends(require_firm_admin),
    db: Session = Depends(get_db),
):
    firm_id = payload["firm_id"]
    updated = db_scripts.update_firm(firm_id, body.model_dump(exclude_none=True), db)
    if not updated:
        raise HTTPException(status_code=404, detail="Firm not found")
    return updated


# ============================================================================
# Rate cards
# ============================================================================

@router.get("/firm/rate-cards")
async def list_rate_cards(
    active_only: bool = True,
    firm_id: str = Depends(get_current_firm_id),
    db: Session = Depends(get_db),
):
    return db_scripts.list_rate_cards(firm_id, db, active_only=active_only)


@router.post("/firm/rate-cards", status_code=status.HTTP_201_CREATED)
async def create_rate_card(
    body: RateCardCreateBody,
    payload: dict = Depends(require_firm_admin),
    db: Session = Depends(get_db),
):
    return db_scripts.create_rate_card(payload["firm_id"], body.model_dump(), db)


@router.patch("/firm/rate-cards/{rate_id}")
async def patch_rate_card(
    rate_id: str,
    body: RateCardUpdateBody,
    payload: dict = Depends(require_firm_admin),
    db: Session = Depends(get_db),
):
    row = db_scripts.update_rate_card(payload["firm_id"], rate_id, body.model_dump(exclude_none=True), db)
    if not row:
        raise HTTPException(status_code=404, detail="Rate card not found")
    return row


@router.delete("/firm/rate-cards/{rate_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rate_card(
    rate_id: str,
    payload: dict = Depends(require_firm_admin),
    db: Session = Depends(get_db),
):
    if not db_scripts.delete_rate_card(payload["firm_id"], rate_id, db):
        raise HTTPException(status_code=404, detail="Rate card not found")
    return None


# ============================================================================
# Team templates
# ============================================================================

@router.get("/firm/team-templates")
async def list_team_templates(
    active_only: bool = True,
    firm_id: str = Depends(get_current_firm_id),
    db: Session = Depends(get_db),
):
    return db_scripts.list_team_templates(firm_id, db, active_only=active_only)


@router.post("/firm/team-templates", status_code=status.HTTP_201_CREATED)
async def create_team_template(
    body: TeamTemplateCreateBody,
    payload: dict = Depends(require_firm_admin),
    db: Session = Depends(get_db),
):
    return db_scripts.create_team_template(payload["firm_id"], body.model_dump(), db)


@router.patch("/firm/team-templates/{template_id}")
async def patch_team_template(
    template_id: str,
    body: TeamTemplateUpdateBody,
    payload: dict = Depends(require_firm_admin),
    db: Session = Depends(get_db),
):
    row = db_scripts.update_team_template(payload["firm_id"], template_id, body.model_dump(exclude_none=True), db)
    if not row:
        raise HTTPException(status_code=404, detail="Team template not found")
    return row


@router.delete("/firm/team-templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_team_template(
    template_id: str,
    payload: dict = Depends(require_firm_admin),
    db: Session = Depends(get_db),
):
    if not db_scripts.delete_team_template(payload["firm_id"], template_id, db):
        raise HTTPException(status_code=404, detail="Team template not found")
    return None


# ============================================================================
# Tech preferences
# ============================================================================

@router.get("/firm/tech-preferences")
async def list_tech_preferences(
    firm_id: str = Depends(get_current_firm_id),
    db: Session = Depends(get_db),
):
    return db_scripts.list_tech_preferences(firm_id, db)


@router.post("/firm/tech-preferences", status_code=status.HTTP_201_CREATED)
async def create_tech_preference(
    body: TechPrefCreateBody,
    payload: dict = Depends(require_firm_admin),
    db: Session = Depends(get_db),
):
    return db_scripts.create_tech_preference(payload["firm_id"], body.model_dump(), db)


@router.patch("/firm/tech-preferences/{pref_id}")
async def patch_tech_preference(
    pref_id: str,
    body: TechPrefUpdateBody,
    payload: dict = Depends(require_firm_admin),
    db: Session = Depends(get_db),
):
    row = db_scripts.update_tech_preference(payload["firm_id"], pref_id, body.model_dump(exclude_none=True), db)
    if not row:
        raise HTTPException(status_code=404, detail="Tech preference not found")
    return row


@router.delete("/firm/tech-preferences/{pref_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tech_preference(
    pref_id: str,
    payload: dict = Depends(require_firm_admin),
    db: Session = Depends(get_db),
):
    if not db_scripts.delete_tech_preference(payload["firm_id"], pref_id, db):
        raise HTTPException(status_code=404, detail="Tech preference not found")
    return None


# ============================================================================
# Past projects (RAG source)
# ============================================================================

@router.get("/firm/past-projects")
async def list_past_projects(
    firm_id: str = Depends(get_current_firm_id),
    db: Session = Depends(get_db),
):
    return db_scripts.list_past_projects(firm_id, db)


@router.get("/firm/past-projects/{project_id}")
async def get_past_project(
    project_id: str,
    firm_id: str = Depends(get_current_firm_id),
    db: Session = Depends(get_db),
):
    row = db_scripts.get_past_project(firm_id, project_id, db)
    if not row:
        raise HTTPException(status_code=404, detail="Past project not found")
    return row


@router.post("/firm/past-projects", status_code=status.HTTP_201_CREATED)
async def create_past_project(
    body: PastProjectCreateBody,
    payload: dict = Depends(require_firm_admin),
    db: Session = Depends(get_db),
):
    firm_id = payload["firm_id"]
    row = db_scripts.create_past_project(firm_id, body.model_dump(), db)
    # Fire-and-log: failing to index doesn't unwind the DB write (the user
    # would otherwise have to re-enter their project to retry indexing).
    try:
        await embed_past_project(firm_id, row)
    except Exception as e:  # noqa: BLE001
        logger.error(f"past-project embed failed for {row.get('project_id')}: {e}")
    return row


@router.patch("/firm/past-projects/{project_id}")
async def patch_past_project(
    project_id: str,
    body: PastProjectUpdateBody,
    payload: dict = Depends(require_firm_admin),
    db: Session = Depends(get_db),
):
    firm_id = payload["firm_id"]
    row = db_scripts.update_past_project(firm_id, project_id, body.model_dump(exclude_none=True), db)
    if not row:
        raise HTTPException(status_code=404, detail="Past project not found")
    try:
        await embed_past_project(firm_id, row)
    except Exception as e:  # noqa: BLE001
        logger.error(f"past-project re-embed failed for {project_id}: {e}")
    return row


@router.delete("/firm/past-projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_past_project(
    project_id: str,
    payload: dict = Depends(require_firm_admin),
    db: Session = Depends(get_db),
):
    firm_id = payload["firm_id"]
    if not db_scripts.delete_past_project(firm_id, project_id, db):
        raise HTTPException(status_code=404, detail="Past project not found")
    try:
        await delete_past_project_embeddings(firm_id, project_id)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"past-project embed cleanup failed for {project_id}: {e}")
    return None


@router.post("/firm/past-projects/bulk")
async def bulk_past_projects(
    file: UploadFile = File(...),
    payload: dict = Depends(require_firm_admin),
    db: Session = Depends(get_db),
):
    """
    CSV columns (header row required):
      project_name, client_name, engagement_type, start_date, end_date,
      summary, original_brief_md, final_report_md, retrospective_md,
      effort_estimated_weeks, effort_actual_weeks
    Markdown fields can be plain text; multi-line values must be CSV-quoted.
    """
    firm_id = payload["firm_id"]
    try:
        raw = (await file.read()).decode("utf-8-sig")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not decode CSV as UTF-8: {e}")

    reader = csv.DictReader(io.StringIO(raw))
    inserted: list[str] = []
    failed: list[dict] = []
    for idx, raw_row in enumerate(reader, start=2):  # row 2 == first data row
        try:
            data = {k: (v.strip() if isinstance(v, str) else v) for k, v in raw_row.items() if v not in (None, "")}
            if "project_name" not in data:
                raise ValueError("project_name is required")
            for fk in ("effort_estimated_weeks", "effort_actual_weeks"):
                if fk in data:
                    data[fk] = float(data[fk])
            row = db_scripts.create_past_project(firm_id, data, db)
            try:
                await embed_past_project(firm_id, row)
            except Exception as ee:  # noqa: BLE001
                logger.error(f"bulk past-project embed failed for {row.get('project_id')}: {ee}")
            inserted.append(row["project_id"])
        except Exception as e:  # noqa: BLE001
            failed.append({"row": idx, "error": str(e)})

    return {"inserted": inserted, "failed": failed}
