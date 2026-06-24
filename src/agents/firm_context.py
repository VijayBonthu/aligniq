"""
Firm context block builder (Bet 3).

Every agent prompt receives a `{firm_context}` interpolation. We render it as
a single markdown block so the LLM has a clear, scannable summary of how the
firm delivers (rate card, tech preferences, an engagement-matched team
template). The block is capped to ~2k tokens by limiting the rate card to the
top-10 most-used roles.

Returns the empty string when the firm has not loaded any context yet —
prompts handle the empty case explicitly (e.g. feasibility omits
cost_breakdown).
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

import database_scripts as db_scripts
from utils.logger import logger


# Roles ranked by how often they tend to show up in engagement teams; we use this
# to truncate large rate cards down to a sensible 10 so the prompt stays lean.
_ROLE_PRIORITY = [
    "Backend Engineer",
    "Frontend Engineer",
    "Full-Stack Engineer",
    "ML Engineer",
    "Data Engineer",
    "DevOps Engineer",
    "Cloud Engineer",
    "Solutions Architect",
    "Product Manager",
    "Engineering Manager",
    "QA Engineer",
    "Designer",
    "Technical Writer",
]


def _format_rate_card(rate_cards: list[dict]) -> str:
    if not rate_cards:
        return "_No rate card loaded._"

    # Stable sort by role priority then seniority, then truncate.
    def _rank(rc: dict) -> tuple[int, str, str]:
        role = rc.get("role") or ""
        try:
            r = _ROLE_PRIORITY.index(role)
        except ValueError:
            r = len(_ROLE_PRIORITY)
        return (r, role, rc.get("seniority") or "")

    sorted_rcs = sorted(rate_cards, key=_rank)
    rows = ["| Role | Seniority | Region | $/hr |", "|------|-----------|--------|-----:|"]
    for rc in sorted_rcs[:10]:
        rate = rc.get("hourly_rate_usd")
        rate_s = f"${rate:.2f}" if isinstance(rate, (int, float)) else "?"
        rows.append(
            f"| {rc.get('role','')} | {rc.get('seniority','')} | {rc.get('region','')} | {rate_s} |"
        )
    if len(sorted_rcs) > 10:
        rows.append(f"\n_… {len(sorted_rcs) - 10} additional roles in firm rate card_")
    return "\n".join(rows)


def _format_tech_prefs(prefs: list[dict]) -> str:
    if not prefs:
        return "_No tech preferences set._"
    lines: list[str] = []
    for p in prefs:
        preferred = p.get("preferred") or []
        anti = p.get("anti_preferred") or []
        line = f"- **{p.get('category','').title()}**: prefer {', '.join(preferred) or '—'}"
        if anti:
            line += f". Flag as risk if customer demands: {', '.join(anti)}"
        rationale = p.get("rationale")
        if rationale:
            line += f". _{rationale}_"
        lines.append(line)
    return "\n".join(lines)


def _format_template(template: Optional[dict]) -> str:
    if not template:
        return "_No engagement-matched template._"
    roles = template.get("roles") or []
    role_lines = [
        f"  - {r.get('count', 1)}× {r.get('seniority','')} {r.get('role','')}"
        + (f" ({r.get('allocation_pct')}%)" if r.get("allocation_pct") else "")
        for r in roles
    ]
    rendered = "\n".join(role_lines) if role_lines else "  _(no roles defined)_"
    out = (
        f"- **{template.get('template_name')}** "
        f"({template.get('engagement_type') or 'generic'})\n{rendered}"
    )
    notes = template.get("notes")
    if notes:
        out += f"\n  _Notes: {notes}_"
    return out


async def build_firm_context_block(
    firm_id: Optional[str],
    engagement_type: Optional[str],
    db: Session,
) -> str:
    """
    Build the markdown <firm_context>...</firm_context> block injected into every
    agent prompt. Returns "" if firm_id is missing — agent prompts treat empty
    firm_context as "no firm guidance, use generic best practice".
    """
    if not firm_id:
        return ""

    try:
        rate_card = db_scripts.list_rate_cards(firm_id, db, active_only=True)
        tech_prefs = db_scripts.list_tech_preferences(firm_id, db)
        template = db_scripts.get_team_template_for_engagement(firm_id, engagement_type, db)
    except Exception as e:  # noqa: BLE001
        logger.error(f"build_firm_context_block failed for firm {firm_id}: {e}")
        return ""

    if not rate_card and not tech_prefs and not template:
        # Firm exists but admin hasn't loaded anything — skip the block to avoid
        # cluttering every prompt with empty markers.
        return ""

    return (
        "<firm_context>\n"
        "## Firm Tech Stack Preferences\n"
        f"{_format_tech_prefs(tech_prefs)}\n\n"
        "## Firm Rate Card (USD/hour)\n"
        f"{_format_rate_card(rate_card)}\n\n"
        "## Default Team Template (engagement-matched)\n"
        f"{_format_template(template)}\n"
        "</firm_context>"
    )
