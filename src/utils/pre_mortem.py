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
from utils.attack_surface import build_attack_surface, vectors_by_id
from utils.logger import logger
from utils.prompts import (
    DEFAULT_PANELIST_BRIEFS,
    FOLLOWUP_ITEMS_MAX,
    FOLLOWUP_ITEMS_MIN,
    PRE_MORTEM_TURN_PROMPT,
    PRE_MORTEM_TURN_PROMPT_V2,
    STARTER_ITEMS_MAX,
    STARTER_ITEMS_MIN,
)


ALLOWED_SEVERITIES = {"high", "med", "low"}
# v2 adds "vector" (an id into the deterministic attack surface); legacy types kept
# so old/degraded reports validate unchanged.
ALLOWED_EVIDENCE_TYPES = {"risk", "assumption", "open_question", "section", "vector"}
ALLOWED_TURN_KINDS = {"starter", "user_question"}
ALLOWED_ITEM_STATUSES = {"open", "added_to_client_qs", "tracked_as_change", "defended"}
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


def _format_panelists_block(panelists: list, surface: Optional[dict] = None, contract: Optional[dict] = None) -> str:
    out = []
    for p in panelists:
        pid = p["id"]
        label = p.get("label", pid)
        if p.get("kind") == "default":
            brief = DEFAULT_PANELIST_BRIEFS.get(pid, label)
            extra = _panelist_brief_context(pid, surface, contract) if surface else ""
            if extra:
                brief = f"{brief} {extra}"
        else:
            concern = p.get("concern", "").strip()
            brief = f"{label}. Custom panelist. Concern/role: {concern or '(no concern given — infer from the label)'}"
        out.append(f"- id=\"{pid}\" — {brief}")
    return "\n".join(out)


def _panelist_brief_context(pid: str, surface: dict, contract: Optional[dict]) -> str:
    """Enrich a default panelist's brief with contract-derived facts so its
    objections are specific to THIS deal (cost band for the CFO, compliance axes
    for the CISO, lock-in/staffing for procurement). Deterministic; best-effort."""
    contract = contract or {}
    scenarios = (surface or {}).get("cost_scenarios")
    if pid == "cfo" and scenarios:
        base = scenarios.get("base", {})
        wc = scenarios.get("worst_case", {})
        bits = [f"This deal: base ${base.get('low_usd',0):,}–${base.get('high_usd',0):,}"]
        if base.get("contingency_pct"):
            bits.append(f"+{base['contingency_pct']:.0f}% contingency")
        if wc.get("adverse_pct"):
            bits.append(f"worst case ${wc.get('low_usd',0):,}–${wc.get('high_usd',0):,}")
        sens = scenarios.get("per_sensitivity") or []
        if sens:
            bits.append("sensitivities: " + "; ".join(s["condition"] for s in sens[:3]))
        return "(THIS DEAL: " + ". ".join(bits) + ".)"
    if pid == "ciso":
        pp = contract.get("problem_profile")
        axes = []
        if isinstance(pp, dict):
            for ax in (pp.get("axes") or []):
                if not isinstance(ax, dict):
                    continue
                name = (ax.get("axis") or "").lower()
                score = ax.get("score") or 0
                if name in ("compliance", "integration", "data") and (isinstance(score, (int, float)) and score >= 3):
                    axes.append(f"{ax.get('axis')} ({ax.get('evidence','')[:60]})")
        if axes:
            return "(THIS DEAL's compliance-relevant axes: " + "; ".join(axes[:3]) + ".)"
    if pid == "procurement":
        gaps = [g.get("needed_role") for g in (contract.get("staffing_gaps") or []) if isinstance(g, dict) and g.get("needed_role")]
        if gaps:
            return f"(THIS DEAL relies on roles the firm may subcontract: {', '.join(gaps[:4])}.)"
    return ""


def _format_vectors_block(vectors: list) -> str:
    """Compact, id-keyed list of objection vectors for the prompt."""
    if not vectors:
        return "(none available)"
    lines = []
    for v in vectors:
        q = f" quote=\"{v['quote']}\"" if v.get("quote") else ""
        lines.append(f"- {v['id']} [{v['vector_type']}] {v['title']}{q} — {v['detail']}")
    return "\n".join(lines)


def _format_cost_facts_block(scenarios: Optional[dict]) -> str:
    """Pre-rendered dollar facts the model may quote but must not recompute."""
    if not scenarios:
        return "(no structured cost model on this report)"
    base = scenarios.get("base", {})
    lines = [f"Base estimate: ${base.get('low_usd',0):,}–${base.get('high_usd',0):,}"
             + (f" (incl. +{base['contingency_pct']:.0f}% contingency)" if base.get("contingency_pct") else "")]
    for s in scenarios.get("per_sensitivity", []):
        sign = "+" if (s["delta_pct"] or 0) >= 0 else ""
        lines.append(f"If \"{s['condition']}\" fires: ${s['scenario_low_usd']:,}–${s['scenario_high_usd']:,} "
                     f"({sign}{s['delta_pct']:.0f}%) [{s['vector_id']}]")
    wc = scenarios.get("worst_case") or {}
    if wc.get("adverse_pct"):
        lines.append(f"Worst case (all adverse hit): ${wc['low_usd']:,}–${wc['high_usd']:,} (+{wc['adverse_pct']:.0f}%) [wc]")
    return "\n".join(lines)


def _quantified_for(vector_ids: list, scenarios: Optional[dict]) -> Optional[dict]:
    """Deterministic dollar scenario for an item that cites a sens-*/wc vector —
    the UI renders this, never the model's prose. First cost vector wins."""
    if not scenarios:
        return None
    per = {s["vector_id"]: s for s in scenarios.get("per_sensitivity", [])}
    for vid in vector_ids:
        if vid in per:
            s = per[vid]
            return {"kind": "sensitivity", "condition": s["condition"], "delta_pct": s["delta_pct"],
                    "scenario_low_usd": s["scenario_low_usd"], "scenario_high_usd": s["scenario_high_usd"]}
        if vid == "wc":
            wc = scenarios.get("worst_case") or {}
            return {"kind": "worst_case", "delta_pct": wc.get("adverse_pct"),
                    "scenario_low_usd": wc.get("low_usd"), "scenario_high_usd": wc.get("high_usd")}
    return None


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


_VECTOR_ID_IN_PROSE = re.compile(r"\b(asm|oq|sens|up|cn|vc|sg|ru|req|risk|lasm|loq)-\d+\b", re.IGNORECASE)


def _strip_vector_ids(text: str, vbyid: dict) -> str:
    """Replace any raw vector id the model leaked into prose with the vector's
    title (the v2 prompt forbids raw ids, but guard anyway)."""
    if not text or not isinstance(text, str):
        return text

    def _sub(m: re.Match) -> str:
        vid = m.group(0).lower()
        v = vbyid.get(vid)
        return f"“{v['title']}”" if v else "(see evidence)"

    return _VECTOR_ID_IN_PROSE.sub(_sub, text)


def _validate_turn_response(
    payload: Any, panelist_ids: list, turn_kind: str, surface: dict, degraded: bool,
    sources: Optional[dict] = None,
) -> tuple[list, list]:
    """
    Validate the LLM turn response. Returns (responses, dropped_items).

    Structural failures (missing responses/panelist, non-dict items) still raise
    HTTPException(502). But an item that cites a vector id which doesn't exist is
    DROPPED (recorded in dropped_items), not fatal — a single hallucinated ref
    shouldn't burn a paid turn. In non-degraded mode every item must carry at
    least one valid `vector` evidence; in degraded mode the legacy evidence rules
    apply unchanged.
    """
    if not isinstance(payload, dict) or "responses" not in payload:
        raise HTTPException(status_code=502, detail="Pre-mortem: missing 'responses' key")
    responses = payload["responses"]
    if not isinstance(responses, list):
        raise HTTPException(status_code=502, detail="Pre-mortem: 'responses' is not a list")

    by_pid = {r.get("panelist_id"): r for r in responses if isinstance(r, dict)}
    missing = [pid for pid in panelist_ids if pid not in by_pid]
    if missing:
        raise HTTPException(status_code=502, detail=f"Pre-mortem: missing responses for panelists {missing}")

    max_items = STARTER_ITEMS_MAX if turn_kind == "starter" else FOLLOWUP_ITEMS_MAX
    vbyid = vectors_by_id(surface)
    scenarios = surface.get("cost_scenarios")
    src = sources or {}
    cleaned, dropped = [], []

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
                dropped.append({"panelist_id": pid, "point_preview": str(it.get("point"))[:80], "reason": "no evidence"})
                continue

            # Drop-guard: any vector evidence must reference an existing vector id.
            bad_ref = False
            vector_ids: list = []
            for ev in evidence:
                if not isinstance(ev, dict) or ev.get("type") not in ALLOWED_EVIDENCE_TYPES or not ev.get("label"):
                    bad_ref = True
                    break
                if ev.get("type") == "vector":
                    vid = ev.get("vector_id")
                    if vid not in vbyid:
                        bad_ref = True
                        break
                    vector_ids.append(vid)
                elif "ref_index" not in ev:
                    ev["ref_index"] = None
            if bad_ref:
                dropped.append({"panelist_id": pid, "point_preview": str(it.get("point"))[:80], "reason": "unknown/invalid evidence ref"})
                continue
            if not degraded and not vector_ids:
                dropped.append({"panelist_id": pid, "point_preview": str(it.get("point"))[:80], "reason": "no vector evidence"})
                continue

            raw_id = it.get("id")
            item_id = raw_id if isinstance(raw_id, str) and raw_id.strip() and raw_id.strip().lower() != "auto" else f"{pid}-{uuid.uuid4().hex[:6]}"
            point = _strip_vector_ids(_strip_placeholders(it["point"], src), vbyid)
            counter = _strip_vector_ids(_strip_placeholders(it["counter_response"], src), vbyid)
            clean_items.append({
                "id": item_id,
                "severity": it["severity"],
                "point": point,
                "counter_response": counter,
                "evidence": evidence,
                "vector_ids": vector_ids,
                "quantified": _quantified_for(vector_ids, scenarios),
                "status": "open",
                "counter_edited": False,
                "came_up": None,
            })

        cleaned.append({"panelist_id": pid, "items": clean_items})

    return cleaned, dropped


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
    contract = report.report_contract if isinstance(report.report_contract, dict) else None
    panelists = thread.get("panelists") or [dict(p) for p in DEFAULT_PANELISTS]
    panelist_ids = [p["id"] for p in panelists]
    if not panelist_ids:
        raise HTTPException(status_code=400, detail="Pre-mortem: no panelists on thread")

    # Deterministic attack surface from the typed contract (+ legacy fallback).
    surface = build_attack_surface(contract, summary)
    degraded = surface["degraded"]

    sources = {
        "key_risks": list(summary.get("key_risks") or []),
        "critical_assumptions": list(summary.get("critical_assumptions") or []),
        "open_questions_for_client": list(summary.get("open_questions_for_client") or []),
    }

    if degraded:
        # Legacy/lite report: behave exactly as v1 (summary blobs, no vectors).
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
            starter_min=STARTER_ITEMS_MIN, starter_max=STARTER_ITEMS_MAX,
            followup_min=FOLLOWUP_ITEMS_MIN, followup_max=FOLLOWUP_ITEMS_MAX,
        )
    else:
        prompt = PRE_MORTEM_TURN_PROMPT_V2.format(
            panelists_block=_format_panelists_block(panelists, surface, contract),
            vectors_block=_format_vectors_block(surface["vectors"]),
            cost_facts_block=_format_cost_facts_block(surface["cost_scenarios"]),
            thread_history=_condense_thread_history(thread.get("turns", [])),
            turn_kind=turn_kind,
            user_message=user_message.strip()[:2000],
            starter_min=STARTER_ITEMS_MIN, starter_max=STARTER_ITEMS_MAX,
            followup_min=FOLLOWUP_ITEMS_MIN, followup_max=FOLLOWUP_ITEMS_MAX,
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

    cleaned, dropped = _validate_turn_response(parsed, panelist_ids, turn_kind, surface, degraded, sources)
    if dropped:
        logger.info(f"Pre-mortem: dropped {len(dropped)} ungrounded item(s) for chat {chat_history_id}")

    turn_id = f"t-{len(thread.get('turns', [])) + 1}"
    new_turn = {
        "id": turn_id,
        "ts": datetime.now(timezone.utc).isoformat(),
        "kind": turn_kind,
        "user_message": user_message.strip(),
        "responses": cleaned,
        "dropped_items": dropped,
    }
    thread.setdefault("turns", []).append(new_turn)
    thread["model"] = model_name
    thread["attack_surface_version"] = 1 if degraded else 2
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
    from database_scripts import _active_report_version_row

    record = _active_report_version_row(chat_history_id, db)
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


# ---------------------------------------------------------------------------
# Defense Brief — a deterministic one-pager for the stakeholder meeting:
# objection → our answer → grounding (real quotes/numbers, never raw ids) →
# status. No LLM. Exported as markdown or PDF by the endpoint.
# ---------------------------------------------------------------------------

_SEV_ORDER = {"high": 0, "med": 1, "low": 2}
_STATUS_GLYPH = {
    "defended": "✓ Defended",
    "added_to_client_qs": "→ Taken to the client",
    "tracked_as_change": "⚙ Tracked as a report change",
    "open": "○ Open",
}


def _brief_item_md(label: str, it: dict, vbyid: dict) -> str:
    out = []
    sev = (it.get("severity") or "").upper()
    out.append(f"**[{sev}] {label}:** {it.get('point', '')}")
    edited = " ✎ (edited)" if it.get("counter_edited") else ""
    out.append(f"- **Our answer{edited}:** {it.get('counter_response', '')}")
    q = it.get("quantified")
    if q and q.get("scenario_low_usd") is not None:
        out.append(f"- **Cost exposure:** ${q['scenario_low_usd']:,}–${q['scenario_high_usd']:,}")
    grounds = []
    for ev in it.get("evidence", []):
        if not isinstance(ev, dict):
            continue
        if ev.get("type") == "vector":
            v = vbyid.get(ev.get("vector_id"))
            if v:
                g = v["title"]
                if v.get("quote"):
                    g += f" — “{v['quote']}”"
                grounds.append(g)
            elif ev.get("label"):
                grounds.append(ev["label"])
        elif ev.get("label"):
            grounds.append(ev["label"])
    if grounds:
        out.append(f"- **Grounding:** {'; '.join(grounds)}")
    if it.get("came_up") is True:
        out.append("- _Came up in the meeting._")
    out.append(f"- _{_STATUS_GLYPH.get(it.get('status', 'open'), it.get('status', 'open'))}_")
    return "\n".join(out)


def build_defense_brief_markdown(thread: dict, surface: Optional[dict], group_by: str = "severity") -> str:
    """Deterministic Defense Brief markdown from a pre-mortem thread. `surface`
    resolves vector ids to real titles/quotes for grounding (never raw ids)."""
    vbyid = vectors_by_id(surface or {})
    items: list[tuple[str, dict]] = []
    for t in thread.get("turns", []):
        for r in t.get("responses", []):
            label = panelist_label(thread, r.get("panelist_id"))
            for it in r.get("items", []):
                items.append((label, it))

    if not items:
        return "# Defense Brief\n\n_No objections have been surfaced yet. Run the Pre-Mortem panel first._\n"

    lines = [
        "# Defense Brief",
        "",
        "_Objections this report invites, our answer to each, and the evidence behind it — prepared for the stakeholder meeting._",
        "",
    ]

    if group_by == "panelist":
        groups: dict[str, list] = {}
        order: list[str] = []
        for label, it in items:
            if label not in groups:
                groups[label] = []
                order.append(label)
            groups[label].append(it)
        for label in order:
            lines.append(f"## {label}")
            lines.append("")
            for it in sorted(groups[label], key=lambda x: _SEV_ORDER.get(x.get("severity"), 9)):
                lines.append(_brief_item_md(label, it, vbyid))
                lines.append("")
    else:
        bysev: dict[str, list] = {"high": [], "med": [], "low": []}
        for label, it in items:
            bysev.setdefault(it.get("severity", "low"), []).append((label, it))
        titles = {"high": "Deal-breakers", "med": "Needs explanation", "low": "Minor pushback"}
        for sev in ("high", "med", "low"):
            if not bysev.get(sev):
                continue
            lines.append(f"## {titles[sev]}")
            lines.append("")
            for label, it in bysev[sev]:
                lines.append(_brief_item_md(label, it, vbyid))
                lines.append("")

    to_client = [it for _l, it in items if it.get("status") == "added_to_client_qs"]
    if to_client:
        lines.append("## Take to the client")
        lines.append("")
        for it in to_client:
            lines.append(f"- {it.get('point', '')}")
        lines.append("")

    return "\n".join(lines)
