"""Cross-version decision index for report versions.

Pure, deterministic helpers that read the typed ReportContract stored per version
(``report_version.report_contract``, a JSON dict) and derive comparable scalars —
cost, timeline, verdict, headline tech — so the chat and the /compare screen can
answer "which version is cheapest / fastest?" and "diff v1 vs v3" WITHOUT skimming
full reports.

Guardrail: every number here is computed in Python (cost via the same
``stitcher.compute_cost`` the report renderer uses) — the LLM never does the math.
Versions without a contract (legacy runs) degrade gracefully to ``has_contract=False``.

The contract is persisted as a plain dict, so we coerce only the sub-pieces we need
(cost lines / sensitivity) into typed models rather than validating the whole
ReportContract, which keeps this robust across schema drift.
"""

from collections import Counter
from typing import List, Optional

from sqlalchemy.orm import Session

import models
from agents.contract import CostLine, Sensitivity
from agents.stitcher import compute_cost
from utils.logger import logger

# Lower verdict rank = better (more favorable go/no-go call).
_VERDICT_RANK = {"go": 0, "go-with-conditions": 1, "conditional-go": 1, "no-go": 2}


def _coerce_cost_lines(raw) -> List[CostLine]:
    out: List[CostLine] = []
    for cl in raw or []:
        try:
            out.append(CostLine(**cl))
        except Exception:
            continue
    return out


def _coerce_sensitivity(raw) -> List[Sensitivity]:
    out: List[Sensitivity] = []
    for s in raw or []:
        try:
            out.append(Sensitivity(**s))
        except Exception:
            continue
    return out


def metrics_from_contract(contract: dict) -> dict:
    """Derive comparable scalars from one stored report_contract dict. Pure."""
    result = {
        "has_contract": True,
        "cost_low": None,
        "cost_high": None,
        "timeline_weeks_low": None,
        "timeline_weeks_high": None,
        "verdict": None,
        "verdict_confidence": None,
        "headline_tech": {},
        "team_count": None,
        "team_fte": None,
        "staffing_gap_count": None,
    }
    if not isinstance(contract, dict):
        result["has_contract"] = False
        return result

    cost_lines = _coerce_cost_lines(contract.get("cost_lines"))
    if cost_lines:
        try:
            cost = compute_cost(
                cost_lines,
                _coerce_sensitivity(contract.get("cost_sensitivity")),
                float(contract.get("contingency_pct") or 0.0),
            )
            result["cost_low"] = round(cost["grand_low"])
            result["cost_high"] = round(cost["grand_high"])
        except Exception as e:  # never let cost math break a comparison
            logger.warning(f"version_compare: compute_cost failed: {e}")

    timeline = contract.get("timeline") or []
    if isinstance(timeline, list) and timeline:
        try:
            result["timeline_weeks_low"] = sum(int(m.get("weeks_low", 0) or 0) for m in timeline)
            result["timeline_weeks_high"] = sum(int(m.get("weeks_high", 0) or 0) for m in timeline)
        except Exception:
            pass

    feas = contract.get("feasibility")
    if isinstance(feas, dict):
        result["verdict"] = feas.get("verdict")
        result["verdict_confidence"] = feas.get("confidence")

    for td in contract.get("tech_decisions") or []:
        if not isinstance(td, dict):
            continue
        layer = (td.get("layer") or "").strip()
        if layer:
            result["headline_tech"][layer] = td.get("choice")

    team = [t for t in (contract.get("team") or []) if isinstance(t, dict)]
    if team:
        result["team_count"] = len(team)
        try:
            result["team_fte"] = round(sum(float(t.get("fte", 0) or 0) for t in team), 2)
        except Exception:
            pass
    gaps = contract.get("staffing_gaps")
    if isinstance(gaps, list):
        # a gap is "real" when the firm's rate-card roster does not cover it
        result["staffing_gap_count"] = sum(
            1 for g in gaps if isinstance(g, dict) and g.get("covered_by_firm") is not True
        )

    return result


async def version_metrics(
    chat_history_id: str, db: Session, versions: Optional[List[int]] = None
) -> List[dict]:
    """Per-version comparable metrics, ascending by version number.

    ``versions`` optionally scopes to a subset (e.g. [1, 3, 4]); default = all.
    Each row carries the typed scalars (when a contract exists) plus changelog /
    is_default / created_at so callers can label and cite every fact by version.
    """
    q = db.query(models.ReportVersions).filter(
        models.ReportVersions.chat_history_id == chat_history_id
    )
    if versions:
        q = q.filter(models.ReportVersions.version_number.in_(versions))
    rows = q.order_by(models.ReportVersions.version_number.asc()).all()

    out: List[dict] = []
    for r in rows:
        row = {
            "version": r.version_number,
            "is_default": bool(r.is_default),
            "changelog": r.changelog_summary,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        contract = r.report_contract if isinstance(r.report_contract, dict) else None
        if contract:
            row.update(metrics_from_contract(contract))
        else:
            row["has_contract"] = False
            sr = r.summary_report if isinstance(r.summary_report, dict) else {}
            row["exec_summary"] = sr.get("executive_summary", "") if isinstance(sr, dict) else ""
        out.append(row)
    return out


def rank_metrics(metrics: List[dict], metric: str) -> List[dict]:
    """Rank version-metric rows by a metric, best first. Rows missing the metric
    are dropped (you can't rank a legacy version on cost it never computed)."""
    m = (metric or "").strip().lower()

    if m in ("cost", "cheapest", "budget", "price"):
        key = lambda r: r.get("cost_low")
    elif m in ("timeline", "fastest", "time", "speed", "duration", "schedule"):
        key = lambda r: r.get("timeline_weeks_low")
    elif m in ("verdict", "feasibility", "go", "recommendation"):
        key = lambda r: _VERDICT_RANK.get((r.get("verdict") or "").lower(), 99)
    else:
        return []

    ranked = [r for r in metrics if key(r) is not None]
    ranked.sort(key=key)
    return ranked


def _tech_by_layer(contract: dict) -> dict:
    """layer -> the full tech_decision dict, so swaps can carry rationale/confidence."""
    out: dict = {}
    for td in (contract.get("tech_decisions") or []):
        if isinstance(td, dict):
            layer = (td.get("layer") or "").strip()
            if layer:
                out.setdefault(layer, td)
    return out


def _team_delta(contract_a: dict, contract_b: dict) -> Optional[dict]:
    """Roster delta aligned by (role, seniority). None when both rosters are empty."""
    def _key(t: dict):
        return ((t.get("role") or "").strip().lower(), (t.get("seniority") or "").strip().lower())

    def _label(t: dict) -> str:
        return f"{(t.get('seniority') or '').strip()} {(t.get('role') or '').strip()}".strip()

    a_list = [t for t in (contract_a.get("team") or []) if isinstance(t, dict)]
    b_list = [t for t in (contract_b.get("team") or []) if isinstance(t, dict)]
    if not a_list and not b_list:
        return None

    a_keys, b_keys = Counter(_key(t) for t in a_list), Counter(_key(t) for t in b_list)
    a_by, b_by = {}, {}
    for t in a_list:
        a_by.setdefault(_key(t), t)
    for t in b_list:
        b_by.setdefault(_key(t), t)

    added = [{"label": _label(b_by[k]), "role": b_by[k].get("role"), "seniority": b_by[k].get("seniority")}
             for k in (b_keys - a_keys)]
    removed = [{"label": _label(a_by[k]), "role": a_by[k].get("role"), "seniority": a_by[k].get("seniority")}
               for k in (a_keys - b_keys)]

    def _fte(lst):
        try:
            return round(sum(float(t.get("fte", 0) or 0) for t in lst), 2)
        except Exception:
            return None

    return {
        "a_count": len(a_list), "b_count": len(b_list),
        "a_fte": _fte(a_list), "b_fte": _fte(b_list),
        "added": added, "removed": removed,
    }


def _staffing_delta(contract_a: dict, contract_b: dict) -> Optional[dict]:
    """New / resolved staffing gaps (firm roster doesn't cover the role). None when nothing changed."""
    def _gaps(c: dict) -> dict:
        out = {}
        for g in (c.get("staffing_gaps") or []):
            if isinstance(g, dict) and g.get("covered_by_firm") is not True:
                out[(g.get("needed_role") or "").strip().lower()] = g
        return out

    ga, gb = _gaps(contract_a), _gaps(contract_b)
    new = [{"needed_role": gb[k].get("needed_role"), "recommendation": gb[k].get("recommendation"),
            "impact": gb[k].get("impact")} for k in gb if k not in ga]
    resolved = [ga[k].get("needed_role") for k in ga if k not in gb]
    if not new and not resolved:
        return None
    return {"new_gaps": new, "resolved_gaps": resolved}


def _timeline_milestone_delta(contract_a: dict, contract_b: dict) -> Optional[dict]:
    """Per-milestone change aligned by name. None when no milestone moved/added/removed."""
    def _by_name(c: dict) -> dict:
        out = {}
        for m in (c.get("timeline") or []):
            if isinstance(m, dict):
                out[(m.get("name") or "").strip()] = m
        return out

    ma, mb = _by_name(contract_a), _by_name(contract_b)
    changed = []
    for name, m in mb.items():
        if name and name in ma:
            la, ha = int(ma[name].get("weeks_low", 0) or 0), int(ma[name].get("weeks_high", 0) or 0)
            lb, hb = int(m.get("weeks_low", 0) or 0), int(m.get("weeks_high", 0) or 0)
            if (la, ha) != (lb, hb):
                changed.append({"name": name, "a_low": la, "a_high": ha, "b_low": lb, "b_high": hb})
    added = [n for n in mb if n and n not in ma]
    removed = [n for n in ma if n and n not in mb]
    if not changed and not added and not removed:
        return None
    return {"changed": changed, "added": added, "removed": removed}


def compute_contract_delta(contract_a: dict, contract_b: dict) -> Optional[dict]:
    """Pairwise typed delta a -> b: cost, timeline, tech swaps (w/ rationale), verdict,
    team roster, staffing gaps, per-milestone timeline.

    Returns None when neither version carries a contract; individual keys are None/empty
    when a metric is absent, so callers fall back to text/exec stats.
    """
    if not isinstance(contract_a, dict) and not isinstance(contract_b, dict):
        return None
    contract_a = contract_a or {}
    contract_b = contract_b or {}

    ma = metrics_from_contract(contract_a)
    mb = metrics_from_contract(contract_b)

    delta: dict = {
        "cost": None, "timeline": None, "tech_swaps": [], "verdict": None,
        "team": None, "staffing": None, "timeline_milestones": None,
    }

    if ma["cost_low"] is not None and mb["cost_low"] is not None:
        d_low = mb["cost_low"] - ma["cost_low"]
        d_high = mb["cost_high"] - ma["cost_high"]
        pct = (d_low / ma["cost_low"] * 100.0) if ma["cost_low"] else None
        delta["cost"] = {
            "a_low": ma["cost_low"], "a_high": ma["cost_high"],
            "b_low": mb["cost_low"], "b_high": mb["cost_high"],
            "delta_low": d_low, "delta_high": d_high,
            "pct": round(pct, 1) if pct is not None else None,
        }

    if ma["timeline_weeks_low"] is not None and mb["timeline_weeks_low"] is not None:
        delta["timeline"] = {
            "a_low": ma["timeline_weeks_low"], "a_high": ma["timeline_weeks_high"],
            "b_low": mb["timeline_weeks_low"], "b_high": mb["timeline_weeks_high"],
            "delta_low": mb["timeline_weeks_low"] - ma["timeline_weeks_low"],
            "delta_high": mb["timeline_weeks_high"] - ma["timeline_weeks_high"],
        }

    ta, tb = ma["headline_tech"], mb["headline_tech"]
    da, db = _tech_by_layer(contract_a), _tech_by_layer(contract_b)
    for layer in sorted(set(ta) | set(tb)):
        ca, cb = ta.get(layer), tb.get(layer)
        if ca and not cb:
            src = da.get(layer, {})
            delta["tech_swaps"].append({"layer": layer, "type": "removed", "from": ca, "to": None,
                                        "rationale": src.get("rationale"), "confidence": src.get("confidence")})
        elif cb and not ca:
            src = db.get(layer, {})
            delta["tech_swaps"].append({"layer": layer, "type": "added", "from": None, "to": cb,
                                        "rationale": src.get("rationale"), "confidence": src.get("confidence")})
        elif ca != cb:
            src = db.get(layer, {})
            delta["tech_swaps"].append({"layer": layer, "type": "changed", "from": ca, "to": cb,
                                        "rationale": src.get("rationale"), "confidence": src.get("confidence")})

    if ma["verdict"] != mb["verdict"]:
        delta["verdict"] = {"from": ma["verdict"], "to": mb["verdict"]}

    delta["team"] = _team_delta(contract_a, contract_b)
    delta["staffing"] = _staffing_delta(contract_a, contract_b)
    delta["timeline_milestones"] = _timeline_milestone_delta(contract_a, contract_b)

    return delta
