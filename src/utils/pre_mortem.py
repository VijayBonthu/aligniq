"""
A6 — Pre-Mortem adversarial panel (thread mode).

Per-turn handler. The user posts a message; one LLM call produces a
structured response from each panelist (CFO/CISO/Procurement plus any
custom panelists the user added). The thread is persisted as JSON on
report_version.pre_mortem so the user can return mid-deal and continue.

State shape on report_version.pre_mortem:

    {
        "report_version_id": "...",
        "model": "gpt-4o-mini",
        "panelists": [
            {"id": "cfo", "label": "Skeptical CFO", "kind": "default"},
            {"id": "ciso", "label": "Paranoid CISO", "kind": "default"},
            {"id": "procurement", "label": "Cost-Conscious Procurement", "kind": "default"},
            {"id": "custom-1", "label": "Their CTO (ex-Stripe)", "kind": "custom",
             "concern": "Postgres maximalist, will push back on NoSQL choices"}
        ],
        "turns": [
            {
                "id": "t-1",
                "ts": "2026-05-08T14:22Z",
                "kind": "starter" | "user_question",
                "user_message": "...",
                "responses": [
                    {"panelist_id": "cfo",
                     "items": [
                         {"id": "t1-cfo-1", "severity": "high",
                          "point": "...", "counter_response": "...",
                          "evidence": [...],
                          "status": "open" | "added_to_client_qs" | "tracked_as_change"}
                     ]}
                ]
            }
        ]
    }
"""

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException, status
from langchain_openai import ChatOpenAI
from sqlalchemy.orm import Session

from config import settings
from database_scripts import get_summary_report
from utils.logger import logger
from utils.prompts import (
    DEFAULT_PANELIST_BRIEFS,
    FOLLOWUP_ITEMS_MAX,
    FOLLOWUP_ITEMS_MIN,
    PRE_MORTEM_TURN_PROMPT,
    STARTER_ITEMS_MAX,
    STARTER_ITEMS_MIN,
)


ALLOWED_SEVERITIES = {"high", "med", "low"}
ALLOWED_EVIDENCE_TYPES = {"risk", "assumption", "open_question", "section"}
ALLOWED_TURN_KINDS = {"starter", "user_question"}
DEFAULT_PANELISTS = [
    {"id": "cfo", "label": "Skeptical CFO", "kind": "default"},
    {"id": "ciso", "label": "Paranoid CISO", "kind": "default"},
    {"id": "procurement", "label": "Cost-Conscious Procurement", "kind": "default"},
]


def empty_thread(report_version_id: str, model: str) -> dict:
    return {
        "report_version_id": report_version_id,
        "model": model,
        "panelists": [dict(p) for p in DEFAULT_PANELISTS],
        "turns": [],
    }


def _truncate(value, max_items: int = 25):
    if isinstance(value, list):
        return value[:max_items]
    return value


def _condense_thread_history(turns: list, max_turns: int = 6) -> str:
    """
    Compact prior turns for prompt continuity. Send only user messages and
    a one-line summary of each item (point text), to keep the prompt bounded.
    """
    if not turns:
        return "(none — this is the first turn)"
    recent = turns[-max_turns:]
    lines = []
    for t in recent:
        kind = t.get("kind", "?")
        user = (t.get("user_message") or "").strip().replace("\n", " ")
        lines.append(f"- [turn {t.get('id','?')} · {kind}] user: {user[:200]}")
        for r in t.get("responses", []):
            pid = r.get("panelist_id", "?")
            for it in r.get("items", []):
                pt = (it.get("point") or "").strip().replace("\n", " ")
                lines.append(f"    {pid}: {pt[:160]}")
    return "\n".join(lines)


def _format_panelists_block(panelists: list) -> str:
    out = []
    for p in panelists:
        pid = p["id"]
        label = p.get("label", pid)
        if p.get("kind") == "default":
            brief = DEFAULT_PANELIST_BRIEFS.get(pid, label)
        else:
            concern = p.get("concern", "").strip()
            brief = f"{label}. Custom panelist. Concern/role: {concern or '(no concern given — infer from the label)'}"
        out.append(f"- id=\"{pid}\" — {brief}")
    return "\n".join(out)


_PLACEHOLDER_PATTERN = re.compile(
    r"\b(KEY[_\s]?RISKS?|CRITICAL[_\s]?ASSUMPTIONS?|OPEN[_\s]?QUESTIONS?(?:[_\s]?FOR[_\s]?CLIENT)?|"
    r"CRITICAL[_\s]?QUESTIONS?|RISKS?|ASSUMPTIONS?|QUESTIONS?)\s*\[\s*(\d+)\s*\]",
    flags=re.IGNORECASE,
)


def _kind_from_token(token: str) -> tuple[str, str]:
    """Map a regex-matched token to (sources_key, human_kind_word)."""
    t = token.lower().replace("_", "").replace(" ", "")
    if "risk" in t:
        return "key_risks", "risk"
    if "assumption" in t:
        return "critical_assumptions", "assumption"
    if "question" in t:
        return "open_questions_for_client", "question"
    return "key_risks", "risk"


def _short_label(item: Any, max_chars: int = 80) -> str:
    if isinstance(item, dict):
        for k in ("title", "name", "summary", "question", "risk", "assumption", "text"):
            v = item.get(k)
            if isinstance(v, str) and v.strip():
                s = v.strip()
                return s if len(s) <= max_chars else s[: max_chars - 1] + "…"
        s = json.dumps(item, default=str)
    else:
        s = str(item).strip()
    return s if len(s) <= max_chars else s[: max_chars - 1] + "…"


def _strip_placeholders(text: str, sources: dict) -> str:
    """
    Replace `KEY_RISKS[2]` / `CRITICAL_ASSUMPTIONS[1]` / etc. in prose with
    "the {kind} '{short label of source[idx]}'". Out-of-range or missing
    sources fall back to "(unspecified)" so the reader is never left with
    a raw identifier.
    """
    if not text or not isinstance(text, str):
        return text

    def _sub(m: re.Match) -> str:
        token, idx_s = m.group(1), m.group(2)
        try:
            idx = int(idx_s)
        except ValueError:
            return "(unspecified)"
        sources_key, kind_word = _kind_from_token(token)
        arr = sources.get(sources_key) or []
        if not isinstance(arr, list) or idx < 0 or idx >= len(arr):
            return "(unspecified)"
        return f"the {kind_word} '{_short_label(arr[idx])}'"

    return _PLACEHOLDER_PATTERN.sub(_sub, text)


def _validate_turn_response(
    payload: Any, panelist_ids: list, turn_kind: str, sources: Optional[dict] = None
) -> list:
    """
    Validate the LLM-produced turn response. Returns the responses list
    (with assigned ids) on success; raises HTTPException(502) on schema
    violations so the caller does not persist a bad turn.
    """
    if not isinstance(payload, dict) or "responses" not in payload:
        raise HTTPException(status_code=502, detail="Pre-mortem: missing 'responses' key")

    responses = payload["responses"]
    if not isinstance(responses, list):
        raise HTTPException(status_code=502, detail="Pre-mortem: 'responses' is not a list")

    by_pid = {r.get("panelist_id"): r for r in responses if isinstance(r, dict)}
    missing = [pid for pid in panelist_ids if pid not in by_pid]
    if missing:
        raise HTTPException(
            status_code=502,
            detail=f"Pre-mortem: missing responses for panelists {missing}",
        )

    if turn_kind == "starter":
        max_items = STARTER_ITEMS_MAX
    else:
        max_items = FOLLOWUP_ITEMS_MAX

    cleaned = []
    for pid in panelist_ids:
        r = by_pid[pid]
        items = r.get("items")
        if not isinstance(items, list):
            raise HTTPException(status_code=502, detail=f"Pre-mortem: {pid} items not a list")
        if len(items) > max_items:
            items = items[:max_items]

        clean_items = []
        for i, it in enumerate(items):
            if not isinstance(it, dict):
                raise HTTPException(status_code=502, detail=f"Pre-mortem: {pid} item {i} not object")
            for fld in ("point", "counter_response", "severity"):
                if not it.get(fld):
                    raise HTTPException(status_code=502, detail=f"Pre-mortem: {pid}-{i} missing '{fld}'")
            if it["severity"] not in ALLOWED_SEVERITIES:
                raise HTTPException(status_code=502, detail=f"Pre-mortem: {pid}-{i} bad severity")

            evidence = it.get("evidence")
            if not isinstance(evidence, list) or len(evidence) == 0:
                raise HTTPException(status_code=502, detail=f"Pre-mortem: {pid}-{i} no evidence")
            for ev in evidence:
                if not isinstance(ev, dict):
                    raise HTTPException(status_code=502, detail=f"Pre-mortem: {pid}-{i} evidence not obj")
                if ev.get("type") not in ALLOWED_EVIDENCE_TYPES:
                    raise HTTPException(status_code=502, detail=f"Pre-mortem: {pid}-{i} bad ev type")
                if not ev.get("label"):
                    raise HTTPException(status_code=502, detail=f"Pre-mortem: {pid}-{i} ev missing label")
                if "ref_index" not in ev:
                    ev["ref_index"] = None

            src = sources or {}
            raw_id = it.get("id")
            item_id = raw_id if isinstance(raw_id, str) and raw_id.strip() and raw_id.strip().lower() != "auto" else f"{pid}-{uuid.uuid4().hex[:6]}"
            clean_items.append({
                "id": item_id,
                "severity": it["severity"],
                "point": _strip_placeholders(it["point"], src),
                "counter_response": _strip_placeholders(it["counter_response"], src),
                "evidence": evidence,
                "status": "open",
            })

        cleaned.append({"panelist_id": pid, "items": clean_items})

    return cleaned


async def run_turn(
    chat_history_id: str,
    db: Session,
    thread: dict,
    user_message: str,
    turn_kind: str,
) -> dict:
    """
    Run one turn against the panel. Mutates+returns the thread with the new
    turn appended. Caller is responsible for persisting the result.
    """
    if turn_kind not in ALLOWED_TURN_KINDS:
        raise HTTPException(status_code=400, detail=f"Pre-mortem: invalid turn kind '{turn_kind}'")
    if not user_message or not user_message.strip():
        raise HTTPException(status_code=400, detail="Pre-mortem: user_message required")

    report = await get_summary_report(chat_history_id, db)
    if not report or not report.report_content or not report.summary_report:
        raise HTTPException(status_code=409, detail="Pre-mortem: full report not yet available")

    summary = report.summary_report if isinstance(report.summary_report, dict) else {}
    panelists = thread.get("panelists") or [dict(p) for p in DEFAULT_PANELISTS]
    panelist_ids = [p["id"] for p in panelists]
    if not panelist_ids:
        raise HTTPException(status_code=400, detail="Pre-mortem: no panelists on thread")

    sources = {
        "key_risks": list(summary.get("key_risks") or []),
        "critical_assumptions": list(summary.get("critical_assumptions") or []),
        "open_questions_for_client": list(summary.get("open_questions_for_client") or []),
    }

    prompt = PRE_MORTEM_TURN_PROMPT.format(
        panelists_block=_format_panelists_block(panelists),
        key_risks_json=json.dumps(_truncate(summary.get("key_risks", [])), default=str)[:6000],
        critical_assumptions_json=json.dumps(_truncate(summary.get("critical_assumptions", [])), default=str)[:6000],
        open_questions_json=json.dumps(_truncate(summary.get("open_questions_for_client", [])), default=str)[:4000],
        recommended_arch_json=json.dumps(summary.get("recommended_architecture") or summary.get("recommended_arch") or {}, default=str)[:5000],
        cost_estimate_json=json.dumps(summary.get("cost_estimate") or summary.get("cost") or {}, default=str)[:2000],
        feasibility_json=json.dumps(summary.get("feasibility") or {}, default=str)[:2000],
        thread_history=_condense_thread_history(thread.get("turns", [])),
        turn_kind=turn_kind,
        user_message=user_message.strip()[:2000],
        starter_min=STARTER_ITEMS_MIN,
        starter_max=STARTER_ITEMS_MAX,
        followup_min=FOLLOWUP_ITEMS_MIN,
        followup_max=FOLLOWUP_ITEMS_MAX,
    )

    model_name = settings.GENERATING_REPORT_MODEL or "gpt-4o-mini"
    llm = ChatOpenAI(
        model=model_name,
        api_key=settings.OPENAI_CHATGPT,
        temperature=0.4,
        model_kwargs={"response_format": {"type": "json_object"}},
    )

    try:
        response = await llm.ainvoke(prompt)
    except Exception as e:
        logger.error(f"Pre-mortem LLM error for chat {chat_history_id}: {e}")
        raise HTTPException(status_code=502, detail=f"Pre-mortem LLM error: {e}")

    raw = response.content if hasattr(response, "content") else str(response)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.error(f"Pre-mortem parse error for chat {chat_history_id}: raw={raw[:500]}")
        raise HTTPException(status_code=502, detail="Pre-mortem: model returned invalid JSON")

    cleaned = _validate_turn_response(parsed, panelist_ids, turn_kind, sources)

    turn_id = f"t-{len(thread.get('turns', [])) + 1}"
    new_turn = {
        "id": turn_id,
        "ts": datetime.now(timezone.utc).isoformat(),
        "kind": turn_kind,
        "user_message": user_message.strip(),
        "responses": cleaned,
    }
    thread.setdefault("turns", []).append(new_turn)
    thread["model"] = model_name
    thread["report_version_id"] = report.report_version_id
    return thread


def find_item(thread: dict, turn_id: str, panelist_id: str, item_id: str) -> Optional[dict]:
    for t in thread.get("turns", []):
        if t.get("id") != turn_id:
            continue
        for r in t.get("responses", []):
            if r.get("panelist_id") != panelist_id:
                continue
            for it in r.get("items", []):
                if it.get("id") == item_id:
                    return it
    return None


def panelist_label(thread: dict, panelist_id: str) -> str:
    for p in thread.get("panelists", []):
        if p.get("id") == panelist_id:
            return p.get("label") or panelist_id
    return panelist_id


_PM_BLOCK_START = "<!-- pre_mortem_questions:start -->"
_PM_BLOCK_END = "<!-- pre_mortem_questions:end -->"
_PM_SUBSECTION_HEADING = "### 3.2.1 Pre-Mortem Surfaced Questions"
_PM_BLOCK_PREAMBLE = (
    "*Questions added during pre-mortem rehearsal. "
    "These will be folded into the canonical Unanswered Questions on the next regeneration.*"
)


def _inject_pre_mortem_question_into_markdown(content: str, new_bullet: str) -> str:
    """
    Idempotent markdown injection. If the marker block exists, append the
    bullet inside it. Otherwise create the sub-section after `### 3.2 …`
    or, failing that, append at the end of the document.
    """
    content = content or ""
    if _PM_BLOCK_START in content and _PM_BLOCK_END in content:
        def _replace(m: re.Match) -> str:
            inner = m.group(2).rstrip()
            return f"{m.group(1)}{inner}\n{new_bullet}\n{m.group(3)}"

        return re.sub(
            r"(" + re.escape(_PM_BLOCK_START) + r")(.*?)(" + re.escape(_PM_BLOCK_END) + r")",
            _replace,
            content,
            count=1,
            flags=re.DOTALL,
        )

    block = (
        f"\n\n{_PM_SUBSECTION_HEADING}\n"
        f"{_PM_BLOCK_START}\n"
        f"{_PM_BLOCK_PREAMBLE}\n\n"
        f"{new_bullet}\n"
        f"{_PM_BLOCK_END}\n"
    )

    heading_match = re.search(r"^###\s+3\.2\b[^\n]*$", content, flags=re.MULTILINE)
    if heading_match:
        after_heading = content[heading_match.end():]
        next_heading = re.search(r"\n#{2,3}\s+", after_heading)
        if next_heading:
            insert_at = heading_match.end() + next_heading.start()
        else:
            insert_at = len(content)
        return content[:insert_at] + block + content[insert_at:]

    return content.rstrip() + block


async def add_to_client_questions(
    chat_history_id: str, item: dict, panelist_label_str: str, db: Session
) -> dict:
    """
    Append the objection's `point` as a question on
    `report_version.summary_report.open_questions_for_client` AND inline it
    into `report_version.report_content` markdown so it's immediately visible
    to the user reading the report.
    """
    from sqlalchemy.orm.attributes import flag_modified
    import models

    record = db.query(models.ReportVersions).filter(
        models.ReportVersions.chat_history_id == chat_history_id
    ).order_by(models.ReportVersions.created_at.desc()).first()
    if not record or not record.summary_report:
        raise HTTPException(status_code=409, detail="Pre-mortem: report not ready")

    summary = dict(record.summary_report) if isinstance(record.summary_report, dict) else {}
    questions = list(summary.get("open_questions_for_client") or [])
    new_q = f"[via Pre-Mortem · {panelist_label_str}] {item['point']}"
    if new_q not in questions:
        questions.append(new_q)
    summary["open_questions_for_client"] = questions
    record.summary_report = summary
    flag_modified(record, "summary_report")

    if record.report_content:
        new_bullet = f"- **[{panelist_label_str}]** {item['point']}"
        record.report_content = _inject_pre_mortem_question_into_markdown(
            record.report_content, new_bullet
        )
        flag_modified(record, "report_content")

    db.commit()
    return {"appended_question": new_q, "total_open_questions": len(questions)}


async def track_as_change(
    chat_history_id: str, item: dict, panelist_label_str: str, db: Session
) -> dict:
    """
    Wrap the existing add_pending_change so a pre-mortem objection becomes a
    pending change against the report. Next regen picks it up.
    """
    from database_scripts import add_pending_change

    user_request = (
        f"[Pre-Mortem · {panelist_label_str}] {item['point']}\n\n"
        f"Drafted counter-response: {item['counter_response']}"
    )
    change = {
        "user_request": user_request,
        "type": "improve_section",
        "source": "pre_mortem",
        "source_item_id": item["id"],
        "panelist": panelist_label_str,
        "severity": item.get("severity"),
    }
    result = await add_pending_change(chat_history_id, change, db)
    return {
        "pending_change_status": result.get("status"),
        "pending_change_id": result.get("change_id"),
    }
