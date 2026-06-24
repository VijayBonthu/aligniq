"""Pre-Mortem v2 — deterministic attack-surface builder.

The report's typed contract already knows its own weak points: every unconfirmed
assumption, open question, cost sensitivity, underplay flag, confidence note,
verdict condition, staffing gap, and research-unanswered item is a precomputed
"objection vector". This module enumerates them in pure Python (zero LLM, zero
hallucination), with stable positional ids and — for cost vectors — real dollar
scenarios from the same `compute_cost` the report renderer uses.

The LLM's job in v2 shrinks to SELECT (which vectors a persona weaponizes), VOICE
(say it in their register), RANK (deal-kill likelihood), and DRAFT (the counter).
Evidence grounding is structural: an item must cite a vector id that exists here.

Legacy reports (no typed contract) degrade to the old summary_report arrays, so
the panel keeps working exactly as before (`degraded=True`).
"""

from __future__ import annotations

import json
from typing import Any, Optional

from agents.contract import CostLine, Sensitivity
from agents.stitcher import compute_cost

# Cap how many vectors go into the prompt (the full set still goes to the sources
# endpoint). Priority-ordered so the sharpest objections survive the cap; ids stay
# positional/stable regardless of the cap.
MAX_PROMPT_VECTORS = 40
_DETAIL_CAP = 300

# Lower = higher priority into the capped prompt set.
_PRIORITY = {
    "underplay": 0,
    "cost_sensitivity": 1,
    "worst_case": 1,
    "verdict_condition": 2,
    "confidence_note": 3,
    "staffing_gap": 4,
    "open_question": 5,
    "assumption": 6,
    "research_unanswered": 7,
    "inferred_requirement": 8,
    "legacy_risk": 9,
    "legacy_assumption": 9,
    "legacy_open_question": 9,
}


def _trunc(s: Any, n: int = _DETAIL_CAP) -> str:
    s = ("" if s is None else str(s)).strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def _label(item: Any, max_chars: int = 90) -> str:
    """A short human label for a legacy source item (string or dict)."""
    if isinstance(item, dict):
        for k in ("title", "name", "summary", "question", "risk", "assumption", "text", "point"):
            v = item.get(k)
            if isinstance(v, str) and v.strip():
                return _trunc(v, max_chars)
        return _trunc(json.dumps(item, default=str), max_chars)
    return _trunc(item, max_chars)


def _cost_scenarios(contract: dict) -> Optional[dict]:
    """Precomputed dollar scenarios per cost sensitivity + the worst case, from the
    typed cost model. None when there are no usable cost lines. Never raises."""
    raw_lines = contract.get("cost_lines") or []
    if not raw_lines:
        return None
    lines: list[CostLine] = []
    for cl in raw_lines:
        try:
            lines.append(CostLine(**cl))
        except Exception:
            continue
    if not lines:
        return None
    sens: list[Sensitivity] = []
    for s in (contract.get("cost_sensitivity") or []):
        try:
            sens.append(Sensitivity(**s))
        except Exception:
            continue
    try:
        contingency = float(contract.get("contingency_pct", 0) or 0)
        cost = compute_cost(lines, sens, contingency)
    except Exception:
        return None

    base_low, base_high = cost["grand_low"], cost["grand_high"]
    per_sensitivity = []
    for i, s in enumerate(sens):
        f = 1.0 + (s.delta_pct or 0) / 100.0
        per_sensitivity.append({
            "vector_id": f"sens-{i}",
            "condition": s.condition,
            "delta_pct": s.delta_pct,
            "scenario_low_usd": round(base_low * f),
            "scenario_high_usd": round(base_high * f),
        })
    return {
        "base": {"low_usd": round(base_low), "high_usd": round(base_high), "contingency_pct": cost["contingency_pct"]},
        "per_sensitivity": per_sensitivity,
        "worst_case": {
            "low_usd": round(cost["worst_case_low"]),
            "high_usd": round(cost["worst_case_high"]),
            "adverse_pct": cost["adverse_sensitivity_pct"],
        },
    }


def _contract_vectors(contract: dict, scenarios: Optional[dict]) -> list[dict]:
    v: list[dict] = []

    for i, a in enumerate(contract.get("global_assumptions") or []):
        if not isinstance(a, str) or not a.strip():
            continue
        v.append({"id": f"asm-{i}", "vector_type": "assumption", "title": _trunc(a, 90),
                  "detail": _trunc(a), "quote": "", "data": {}, "source": {"type": "assumption", "ref_index": None}})

    # validated_requirements is planner-free-form; only emit inferred rows we can read.
    vr = contract.get("validated_requirements")
    if isinstance(vr, dict):
        idx = 0
        for rows in vr.values():
            if not isinstance(rows, list):
                continue
            for r in rows:
                if not isinstance(r, dict):
                    continue
                if (r.get("source") or "").lower() != "inferred":
                    continue
                text = r.get("text") or r.get("requirement") or r.get("name")
                if not isinstance(text, str) or not text.strip():
                    continue
                v.append({"id": f"req-{idx}", "vector_type": "inferred_requirement", "title": _trunc(text, 90),
                          "detail": _trunc(text), "quote": "", "data": {}, "source": {"type": "section", "ref_index": None}})
                idx += 1

    for i, q in enumerate(contract.get("open_questions_for_client") or []):
        if isinstance(q, dict):
            qt = q.get("question") or ""
            why = q.get("why_it_matters") or ""
            sev = q.get("severity") or ""
        else:
            qt, why, sev = str(q), "", ""
        if not qt:
            continue
        v.append({"id": f"oq-{i}", "vector_type": "open_question", "title": _trunc(qt, 90),
                  "detail": _trunc(why or qt), "quote": "", "data": {"severity": sev},
                  "source": {"type": "open_question", "ref_index": i}})

    if scenarios:
        for entry in scenarios.get("per_sensitivity", []):
            # vector_id is sens-{i} already
            i = entry["vector_id"].split("-")[1]
            v.append({"id": entry["vector_id"], "vector_type": "cost_sensitivity",
                      "title": _trunc(entry["condition"], 90),
                      "detail": f"If this fires: ${entry['scenario_low_usd']:,}–${entry['scenario_high_usd']:,} "
                                f"({'+' if (entry['delta_pct'] or 0) >= 0 else ''}{entry['delta_pct']:.0f}%).",
                      "quote": "", "data": entry, "source": {"type": "section", "ref_index": None}})
        wc = scenarios.get("worst_case") or {}
        if wc.get("adverse_pct"):
            v.append({"id": "wc", "vector_type": "worst_case", "title": "Worst case — all adverse conditions hit",
                      "detail": f"If every adverse sensitivity fires: ${wc['low_usd']:,}–${wc['high_usd']:,} "
                                f"(+{wc['adverse_pct']:.0f}% over base).",
                      "quote": "", "data": wc, "source": {"type": "section", "ref_index": None}})

    for i, f in enumerate(contract.get("underplay_flags") or []):
        if not isinstance(f, dict):
            continue
        quote = f.get("quote") or ""
        detail = f"Stated as '{f.get('stated_as','')}' but usually involves {f.get('usually_involves','')}. {f.get('effort_note','')}".strip()
        v.append({"id": f"up-{i}", "vector_type": "underplay",
                  "title": _trunc(f"Client understated: \"{quote}\"" if quote else (f.get("stated_as") or "Underplayed scope"), 90),
                  "detail": _trunc(detail), "quote": quote, "data": {}, "source": {"type": "section", "ref_index": None}})

    for i, n in enumerate(contract.get("confidence_notes") or []):
        if not isinstance(n, str) or not n.strip():
            continue
        v.append({"id": f"cn-{i}", "vector_type": "confidence_note", "title": _trunc(n, 90),
                  "detail": _trunc(n), "quote": "", "data": {}, "source": {"type": "section", "ref_index": None}})

    feas = contract.get("feasibility")
    if isinstance(feas, dict):
        verdict = feas.get("verdict")
        for i, c in enumerate(feas.get("conditions") or []):
            if not isinstance(c, str) or not c.strip():
                continue
            v.append({"id": f"vc-{i}", "vector_type": "verdict_condition", "title": _trunc(c, 90),
                      "detail": _trunc(c), "quote": "", "data": {"verdict": verdict, "confidence": feas.get("confidence")},
                      "source": {"type": "section", "ref_index": None}})

    for i, g in enumerate(contract.get("staffing_gaps") or []):
        if not isinstance(g, dict):
            continue
        role = g.get("needed_role") or "role"
        v.append({"id": f"sg-{i}", "vector_type": "staffing_gap", "title": _trunc(f"Staffing gap: {role}", 90),
                  "detail": _trunc(f"{g.get('recommendation','')} — {g.get('impact','')}"),
                  "quote": "", "data": {}, "source": {"type": "section", "ref_index": None}})

    dossier = contract.get("research_dossier")
    if isinstance(dossier, dict):
        for i, u in enumerate(dossier.get("unanswered") or []):
            if not isinstance(u, str) or not u.strip():
                continue
            v.append({"id": f"ru-{i}", "vector_type": "research_unanswered", "title": _trunc(u, 90),
                      "detail": _trunc(u), "quote": "", "data": {}, "source": {"type": "section", "ref_index": None}})

    return v


def _legacy_vectors(summary: dict) -> list[dict]:
    """Vectors from summary_report only — the sole source on legacy/lite reports.
    Keeps `source.ref_index` so the existing evidence chips still resolve."""
    v: list[dict] = []
    for i, r in enumerate(summary.get("key_risks") or []):
        v.append({"id": f"risk-{i}", "vector_type": "legacy_risk", "title": _label(r),
                  "detail": _label(r, _DETAIL_CAP), "quote": "", "data": {}, "source": {"type": "risk", "ref_index": i}})
    for i, a in enumerate(summary.get("critical_assumptions") or []):
        v.append({"id": f"lasm-{i}", "vector_type": "legacy_assumption", "title": _label(a),
                  "detail": _label(a, _DETAIL_CAP), "quote": "", "data": {}, "source": {"type": "assumption", "ref_index": i}})
    for i, q in enumerate(summary.get("open_questions_for_client") or []):
        v.append({"id": f"loq-{i}", "vector_type": "legacy_open_question", "title": _label(q),
                  "detail": _label(q, _DETAIL_CAP), "quote": "", "data": {}, "source": {"type": "open_question", "ref_index": i}})
    return v


def build_attack_surface(contract: Optional[dict], summary: dict) -> dict:
    """Enumerate objection vectors from the typed contract (+ legacy summary fallback).

    Returns {"vectors": [...], "cost_scenarios": {...}|None, "degraded": bool}.
    `vectors` is priority-capped for the prompt; ids are stable/positional.
    """
    summary = summary if isinstance(summary, dict) else {}
    degraded = not isinstance(contract, dict)

    scenarios = None if degraded else _cost_scenarios(contract)
    vectors = _legacy_vectors(summary) if degraded else _contract_vectors(contract, scenarios)

    # If a typed contract produced no vectors (unusual), fall back to legacy so the
    # panel still has something to weaponize.
    if not degraded and not vectors:
        vectors = _legacy_vectors(summary)
        degraded = True
        scenarios = None

    vectors.sort(key=lambda v: _PRIORITY.get(v["vector_type"], 99))
    return {"vectors": vectors[:MAX_PROMPT_VECTORS], "cost_scenarios": scenarios, "degraded": degraded}


def vectors_by_id(surface: dict) -> dict:
    return {v["id"]: v for v in surface.get("vectors", [])}
