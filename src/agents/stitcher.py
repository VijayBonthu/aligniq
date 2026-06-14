"""Deterministic stitcher — renders a ReportContract + written section bodies to markdown.

No LLM. The old `ba_final_report_generation` was a ~30K-input-token aggregator;
this replaces it. Writers already produce per-section markdown; this layer
owns headers, section ordering, the Executive Summary commit-line, the Open
Questions appendix, and the Global Assumptions block.

Keeping this LLM-free is what lets the stitcher be golden-file-tested. Any
non-determinism in the final markdown means a bug in a writer, not in stitching.
"""

import re
from typing import Optional

from agents.contract import (
    ApproachOption,
    ClientQA,
    CostLine,
    FeasibilityVerdict,
    KnownIssue,
    Milestone,
    OpenQuestion,
    ProblemProfile,
    ReportContract,
    ResearchDossier,
    Sensitivity,
    StaffingGap,
    TeamRole,
    TechDecision,
    UnderplayFlag,
)


def _section_block(heading_level: int, title: str, body_md: str) -> str:
    """Emit a heading + body. body_md is trusted to already be valid markdown."""
    hashes = "#" * heading_level
    return f"{hashes} {title}\n\n{body_md.rstrip()}\n"


def _open_questions_block(questions: list[OpenQuestion]) -> str:
    if not questions:
        return ""
    lines = ["## Open Questions for Client", ""]
    severity_order = {"blocker": 0, "high": 1, "medium": 2, "low": 3}
    ordered = sorted(questions, key=lambda q: severity_order.get(q.severity, 99))
    for q in ordered:
        anchor = f" (re: {q.related_section_id})" if q.related_section_id else ""
        lines.append(f"- **[{q.severity}]** {q.question}{anchor}")
        lines.append(f"  - Why it matters: {q.why_it_matters}")
    lines.append("")
    return "\n".join(lines)


def _global_assumptions_block(assumptions: list[str]) -> str:
    if not assumptions:
        return ""
    lines = ["## Global Assumptions", ""]
    for a in assumptions:
        lines.append(f"- {a}")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Decision-artifact rendering. All deterministic — the cost math is Python,
# never an LLM. compute_cost is exported so it can be unit-tested directly.
# ---------------------------------------------------------------------------


def _money(x: float) -> str:
    """Render a dollar amount with thousands separators, no cents."""
    return f"${x:,.0f}"


def compute_cost(
    cost_lines: list[CostLine],
    sensitivity: list[Sensitivity],
    contingency_pct: float,
) -> dict:
    """Compute line subtotals, per-workstream rollup, and contingency-adjusted totals.

    Pure function — `hours x rate` is done here, not by any LLM. Returns a dict
    the cost-table renderer consumes; also independently unit-testable.
    """
    lines: list[dict] = []
    subtotal_low = 0.0
    subtotal_high = 0.0
    by_workstream: dict[str, list[float]] = {}

    for cl in cost_lines:
        line_low = cl.hours_low * cl.rate_usd
        line_high = cl.hours_high * cl.rate_usd
        lines.append({
            "workstream": cl.workstream,
            "role": cl.role,
            "seniority": cl.seniority,
            "region": cl.region,
            "hours_low": cl.hours_low,
            "hours_high": cl.hours_high,
            "rate_usd": cl.rate_usd,
            "rate_card_ref": cl.rate_card_ref,
            "cost_low": line_low,
            "cost_high": line_high,
        })
        subtotal_low += line_low
        subtotal_high += line_high
        ws = by_workstream.setdefault(cl.workstream, [0.0, 0.0])
        ws[0] += line_low
        ws[1] += line_high

    factor = 1.0 + (contingency_pct or 0.0) / 100.0
    grand_low = subtotal_low * factor
    grand_high = subtotal_high * factor

    # Worst-case rollup: every adverse sensitivity condition hitting at once
    # (additive, upside deltas excluded). Stakeholders ask "and if it all goes
    # wrong?" — answer it deterministically instead of leaving it to prose.
    adverse_pct = sum(s.delta_pct for s in (sensitivity or []) if s.delta_pct > 0)
    worst_factor = 1.0 + adverse_pct / 100.0

    return {
        "lines": lines,
        "subtotal_low": subtotal_low,
        "subtotal_high": subtotal_high,
        "contingency_pct": contingency_pct or 0.0,
        "grand_low": grand_low,
        "grand_high": grand_high,
        "by_workstream": by_workstream,
        "adverse_sensitivity_pct": adverse_pct,
        "worst_case_low": grand_low * worst_factor,
        "worst_case_high": grand_high * worst_factor,
    }


def _feasibility_block(v: FeasibilityVerdict) -> str:
    label = (v.verdict or "").replace("-", " ").upper() or "UNDETERMINED"
    conf = f" ({v.confidence} confidence)" if v.confidence else ""
    lines = [f"> **Feasibility verdict: {label}{conf}**", ">"]
    if v.conditions:
        lines.append("> Conditions:")
        for c in v.conditions:
            lines.append(f"> - {c}")
    if v.risks_driving_verdict:
        lines.append("> Key risks driving this verdict:")
        for r in v.risks_driving_verdict:
            lines.append(f"> - {r}")
    lines.append("")
    return "\n".join(lines)


def _tech_stack_table(decisions: list[TechDecision]) -> str:
    lines = ["### Recommended Tech Stack", ""]
    lines.append("| Layer | Choice | Alternatives | Rationale | Confidence |")
    lines.append("|-------|--------|--------------|-----------|------------|")
    for d in decisions:
        alts = ", ".join(d.alternatives) or "—"
        flag = "" if d.honors_firm_pref else " ⚠️ (against firm preference)"
        choice = f"{d.choice}{flag}"
        rationale = d.rationale.replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {d.layer} | {choice} | {alts} | {rationale} | {d.confidence} |")
    lines.append("")
    return "\n".join(lines)


def _cost_table(cost: dict) -> str:
    lines = ["### Cost & Effort Estimate", ""]
    # Rates source line — make it explicit whether the $/hr is the firm's own
    # rate card or a market estimate, so the most-challenged number in the report
    # carries its provenance.
    total_lines = len(cost["lines"])
    firm_grounded = sum(1 for ln in cost["lines"] if (ln.get("rate_card_ref") or "").startswith("firm:"))
    if total_lines:
        if firm_grounded == total_lines:
            lines.append("_Rates: your firm rate card._")
        elif firm_grounded:
            lines.append(
                f"_Rates: your firm rate card ({firm_grounded} of {total_lines} roles); "
                "market estimates for the rest (see Confidence Notes)._"
            )
        else:
            lines.append("_Rates: market estimates — load your firm rate card for firm-grounded numbers._")
        lines.append("")
    lines.append("| Workstream | Role | Hours (low–high) | Rate | Cost (low–high) | Rate-card ref |")
    lines.append("|------------|------|------------------|------|-----------------|---------------|")
    for ln in cost["lines"]:
        role = ln["role"] + (f" ({ln['seniority']})" if ln["seniority"] else "")
        hours = f"{ln['hours_low']}–{ln['hours_high']}"
        cost_range = f"{_money(ln['cost_low'])}–{_money(ln['cost_high'])}"
        ref = ln["rate_card_ref"] or "—"
        lines.append(
            f"| {ln['workstream']} | {role} | {hours} | {_money(ln['rate_usd'])}/hr | {cost_range} | {ref} |"
        )
    lines.append("")
    lines.append(f"- **Subtotal:** {_money(cost['subtotal_low'])} – {_money(cost['subtotal_high'])}")
    if cost["contingency_pct"]:
        lines.append(f"- **Contingency:** +{cost['contingency_pct']:.0f}%")
    lines.append(f"- **Total estimate:** **{_money(cost['grand_low'])} – {_money(cost['grand_high'])}**")
    if cost.get("adverse_sensitivity_pct"):
        lines.append(
            f"- **Worst case (all adverse sensitivity conditions hit, +{cost['adverse_sensitivity_pct']:.0f}%):** "
            f"{_money(cost['worst_case_low'])} – {_money(cost['worst_case_high'])}"
        )
    if len(cost["by_workstream"]) > 1:
        lines.append("")
        lines.append("By workstream:")
        for ws, (low, high) in cost["by_workstream"].items():
            lines.append(f"  - {ws}: {_money(low)} – {_money(high)}")
    lines.append("")
    return "\n".join(lines)


def _sensitivity_block(sensitivity: list[Sensitivity]) -> str:
    lines = ["### Estimate Sensitivity", ""]
    for s in sensitivity:
        sign = "+" if s.delta_pct >= 0 else ""
        lines.append(f"- {s.condition}: {sign}{s.delta_pct:.0f}%")
    lines.append("")
    return "\n".join(lines)


def _timeline_table(milestones: list[Milestone]) -> str:
    lines = ["### Phased Roadmap", ""]
    lines.append("| Milestone | Duration (weeks) | Depends on | Deliverables |")
    lines.append("|-----------|------------------|------------|--------------|")
    for m in milestones:
        dur = f"{m.weeks_low}–{m.weeks_high}"
        deps = ", ".join(m.depends_on) or "—"
        delivs = ", ".join(m.deliverables) or "—"
        lines.append(f"| {m.name} | {dur} | {deps} | {delivs} |")
    lines.append("")
    return "\n".join(lines)


_PROVIDER_LABEL = {"aws": "AWS", "azure": "Azure", "gcp": "GCP", "oss": "OSS", "other": "Other"}


def _md_cell(text: str) -> str:
    return (text or "—").replace("|", "\\|").replace("\n", " ")


def _service_options_block(decisions: list[TechDecision]) -> str:
    """The cloud-options matrix: per tech choice, the concrete service on each
    provider WITH what bites you, cost class, and lock-in — so choosing between
    AWS / Azure / GCP / OSS is a table read, not a research project. Falls back
    to the compact one-liner when no option carries the depth fields."""
    rows = [d for d in decisions if d.service_options]
    if not rows:
        return ""

    has_depth = any(
        (o.limits or o.cost_class or o.lockin_note)
        for d in rows for o in d.service_options
    )
    if not has_depth:
        lines = ["**Cloud / OSS service options:**", ""]
        for d in rows:
            opts = "; ".join(
                f"{_PROVIDER_LABEL.get(o.provider, o.provider)}: {o.service}"
                + (f" ({o.note})" if o.note else "")
                for o in d.service_options
            )
            lines.append(f"- **{d.choice}** — {opts}")
        lines.append("")
        return "\n".join(lines)

    lines = ["### Cloud / OSS Options — What Bites You", ""]
    lines.append(
        "_Per recommended technology: the concrete service on each provider, its production "
        "limitation, rough cost class, and switching cost. Sourced rows link the research; "
        "unsourced rows are expert judgment._"
    )
    lines.append("")
    for d in rows:
        lines.append(f"**{d.choice}** ({d.layer})")
        lines.append("")
        lines.append("| Provider | Service | What bites you | Cost | Lock-in | Source |")
        lines.append("|----------|---------|----------------|------|---------|--------|")
        for o in d.service_options:
            provider = _PROVIDER_LABEL.get(o.provider, o.provider)
            src = f"[source]({o.source_url})" if o.source_url else "—"
            lines.append(
                f"| {provider} | {_md_cell(o.service)} | {_md_cell(o.limits or o.note)} "
                f"| {_md_cell(o.cost_class)} | {_md_cell(o.lockin_note)} | {src} |"
            )
        lines.append("")
    return "\n".join(lines)


def _team_table(team: list[TeamRole]) -> str:
    lines = ["### Team Composition", ""]
    lines.append("| Role | Seniority | FTE | Duration (weeks) | Firm staffs it? |")
    lines.append("|------|-----------|----:|-----------------:|-----------------|")
    for t in team:
        if t.in_firm_roster is True:
            roster = "yes"
        elif t.in_firm_roster is False:
            roster = "⚠ gap"
        else:
            roster = "—"
        lines.append(f"| {t.role} | {t.seniority or '—'} | {t.fte:g} | {t.duration_weeks} | {roster} |")
    lines.append("")
    return "\n".join(lines)


def _staffing_gaps_block(gaps: list[StaffingGap]) -> str:
    lines = ["### Staffing Gaps", ""]
    for g in gaps:
        lines.append(f"- **{g.needed_role}** — {g.recommendation}. {g.impact}")
    lines.append("")
    return "\n".join(lines)


def _known_issues_section(issues: list[KnownIssue]) -> str:
    """Top-level section. Source is always a clickable link, never a bare URL."""
    severity_order = {"high": 0, "medium": 1, "low": 2}
    ordered = sorted(issues, key=lambda i: severity_order.get(i.severity, 99))
    lines = ["## Known Issues & Integration Gotchas", ""]
    for i in ordered:
        lines.append(f"### {i.area}")
        lines.append(f"- **Issue** [{i.severity}]: {i.issue}")
        if i.symptom:
            lines.append(f"- **Symptom:** {i.symptom}")
        lines.append(f"- **Workaround:** {i.workaround}")
        source = f"[source]({i.source_url})" if i.source_url else "(no source)"
        lines.append(f"- **Source:** {source} · confidence: {i.confidence}")
        lines.append("")
    return "\n".join(lines)


# Decision tables attach to these standard section slugs (see PLANNER_PROMPT
# REQUIRED SECTIONS). When the anchor section exists, the table renders right
# after that section's prose; otherwise it falls back to a standalone block so
# nothing decision-grade is ever silently dropped.
def _tables_for_section(contract: ReportContract, section_id: str) -> list[str]:
    blocks: list[str] = []
    if section_id == "proposed-architecture" and contract.tech_decisions:
        blocks.append(_tech_stack_table(contract.tech_decisions))
        blocks.append(_service_options_block(contract.tech_decisions))
    if section_id == "feasibility-and-cost":
        if contract.cost_lines:
            blocks.append(_cost_table(compute_cost(
                contract.cost_lines, contract.cost_sensitivity, contract.contingency_pct,
            )))
        if contract.cost_sensitivity:
            blocks.append(_sensitivity_block(contract.cost_sensitivity))
        if contract.timeline:
            blocks.append(_timeline_table(contract.timeline))
        if contract.team:
            blocks.append(_team_table(contract.team))
        if contract.staffing_gaps:
            blocks.append(_staffing_gaps_block(contract.staffing_gaps))
    return blocks


def _orphan_decision_blocks(contract: ReportContract, rendered_section_ids: set[str]) -> str:
    """Render any decision tables whose anchor section was not produced, so the
    decisions still appear in the report."""
    blocks: list[str] = []
    if contract.tech_decisions and "proposed-architecture" not in rendered_section_ids:
        blocks.append(_tech_stack_table(contract.tech_decisions))
        blocks.append(_service_options_block(contract.tech_decisions))
    if "feasibility-and-cost" not in rendered_section_ids:
        if contract.cost_lines:
            blocks.append(_cost_table(compute_cost(
                contract.cost_lines, contract.cost_sensitivity, contract.contingency_pct,
            )))
        if contract.cost_sensitivity:
            blocks.append(_sensitivity_block(contract.cost_sensitivity))
        if contract.timeline:
            blocks.append(_timeline_table(contract.timeline))
        if contract.team:
            blocks.append(_team_table(contract.team))
        if contract.staffing_gaps:
            blocks.append(_staffing_gaps_block(contract.staffing_gaps))
    if not blocks:
        return ""
    return "## Solution & Estimate\n\n" + "\n".join(b for b in blocks if b)


# ---------------------------------------------------------------------------
# Answer-first lead (Minto): the report opens with the recommendation, the
# headline numbers, and the verdict — not with prose that builds to a conclusion.
# ---------------------------------------------------------------------------


def _timeline_span_weeks(milestones: list[Milestone]) -> tuple[int, int]:
    """End-to-end duration as the critical path through the milestone DAG.

    Longest dependency chain (not a naive sum, which double-counts parallel
    phases). Cycle-safe via the `seen` set. Returns (low_weeks, high_weeks).
    """
    by_name = {m.name: m for m in milestones}

    def finish(name: str, hi: bool, seen: frozenset[str]) -> int:
        m = by_name.get(name)
        if m is None or name in seen:
            return 0
        seen = seen | {name}
        dep_finishes = [finish(d, hi, seen) for d in m.depends_on if d in by_name]
        return max(dep_finishes or [0]) + (m.weeks_high if hi else m.weeks_low)

    low = max((finish(m.name, False, frozenset()) for m in milestones), default=0)
    high = max((finish(m.name, True, frozenset()) for m in milestones), default=0)
    return low, high


def _headline_line(contract: ReportContract) -> str:
    """One line with the numbers a stakeholder challenges first: cost and time."""
    bits: list[str] = []
    if contract.cost_lines:
        cost = compute_cost(contract.cost_lines, contract.cost_sensitivity, contract.contingency_pct)
        bits.append(f"**Estimate:** {_money(cost['grand_low'])} – {_money(cost['grand_high'])}")
    if contract.timeline:
        low, high = _timeline_span_weeks(contract.timeline)
        if high:
            span = f"{low}–{high}" if low != high else f"{high}"
            bits.append(f"**Timeline (end-to-end):** {span} weeks")
    return " · ".join(bits)


def _bottom_line_block(contract: ReportContract) -> str:
    """Recommendation up front: commit-line + headline numbers + verdict."""
    brief = (contract.executive_summary_brief or "").strip()
    headline = _headline_line(contract)
    if not brief and not headline and not contract.feasibility:
        return ""
    lines = ["## Bottom Line", ""]
    if brief:
        lines.append(brief)
        lines.append("")
    if headline:
        lines.append(headline)
        lines.append("")
    if contract.feasibility:
        lines.append(_feasibility_block(contract.feasibility).rstrip())
        lines.append("")
    return "\n".join(lines)


def _engagement_brief_block(contract: ReportContract) -> str:
    """The engagement story up front: the problem, what we asked, what they told us.

    Pure render of typed fields the planner lifts from the CRD's confirmed Q&A —
    so the deliverable shows the problem and the client's own answers in context,
    instead of burying them in inline quotes. Open (unanswered) items stay in the
    Open Questions appendix at the end.
    """
    problem = (contract.problem_statement or "").strip()
    answered = [q for q in contract.client_qa if (q.question or "").strip() and (q.answer or "").strip()]
    if not problem and not answered:
        return ""
    lines = ["## Engagement Brief", ""]
    if problem:
        lines.append("### The Problem")
        lines.append("")
        lines.append(problem)
        lines.append("")
    if answered:
        lines.append("### What We Asked / What You Told Us")
        lines.append("")
        lines.append("| Question | What the client told us | Ref |")
        lines.append("|----------|-------------------------|-----|")
        for q in answered:
            ques = q.question.replace("|", "\\|").replace("\n", " ")
            ans = q.answer.replace("|", "\\|").replace("\n", " ")
            ref = (q.source or "—").replace("|", "\\|")
            lines.append(f"| {ques} | {ans} | {ref} |")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# The crux + the approaches — the spine of a specialist's answer. These lead the
# report so it reads as "here is the hard problem and the 2-3 real ways to solve
# it", not as a generic scope doc.
# ---------------------------------------------------------------------------


def _core_challenge_block(core_challenge: str) -> str:
    text = (core_challenge or "").strip()
    if not text:
        return ""
    return "## The Core Challenge\n\n" + text + "\n"


def _problem_shape_block(profile: Optional[ProblemProfile]) -> str:
    """Compact render of the problem diagnosis: delivery mode + dominant axes."""
    if profile is None:
        return ""
    has_axes = bool(profile.axes)
    if not (profile.delivery_mode or profile.summary or has_axes):
        return ""
    lines = ["## Problem Shape", ""]
    if profile.summary:
        lines.append(profile.summary)
        lines.append("")
    mode = (profile.delivery_mode or "").strip()
    if mode:
        lines.append(f"**Delivery mode:** {mode}")
        lines.append("")
    if has_axes:
        dominant = {a.strip().lower() for a in profile.dominant_axes}
        ordered = sorted(profile.axes, key=lambda a: -a.score)
        lines.append("| Dimension | Weight (0–5) | Why |")
        lines.append("|-----------|-------------:|-----|")
        for ax in ordered:
            name = ax.axis.replace("|", "\\|")
            if name.strip().lower() in dominant:
                name = f"**{name}**"
            evidence = (ax.evidence or "—").replace("|", "\\|").replace("\n", " ")
            lines.append(f"| {name} | {ax.score} | {evidence} |")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Reality Gap — the two-sided bias corrector. Client side: quote-anchored
# understatements in their own document. Firm side: roles/tech the firm can't
# cover as-is. Closing this gap at signing time is the product's headline pitch.
# ---------------------------------------------------------------------------


def _reality_gap_section(contract: ReportContract) -> str:
    flags = contract.underplay_flags or []
    gaps = contract.staffing_gaps or []
    off_pref = [d for d in (contract.tech_decisions or []) if not d.honors_firm_pref]
    if not flags and not gaps and not off_pref:
        return ""
    lines = ["## Reality Gap — Stated vs. Likely-Actual", ""]
    if flags:
        lines.append("### What the brief understates")
        lines.append("")
        lines.append("| The brief says | Reads as | What it usually involves | Effort note |")
        lines.append("|----------------|----------|--------------------------|-------------|")
        for f in flags:
            quote = f.quote.replace("|", "\\|").replace("\n", " ")
            stated = f.stated_as.replace("|", "\\|").replace("\n", " ")
            actual = f.usually_involves.replace("|", "\\|").replace("\n", " ")
            note = (f.effort_note or "—").replace("|", "\\|").replace("\n", " ")
            lines.append(f"| “{quote}” | {stated} | {actual} | {note} |")
        lines.append("")
    if gaps or off_pref:
        lines.append("### Delivery-side fit")
        lines.append("")
        for g in gaps:
            lines.append(f"- **Staffing gap — {g.needed_role}:** {g.recommendation}. {g.impact}")
        for d in off_pref:
            lines.append(
                f"- **Off-preference tech — {d.choice}** ({d.layer}): {d.rationale}"
            )
        lines.append("")
    if contract.contingency_pct:
        drivers: list[str] = []
        if flags:
            drivers.append(f"{len(flags)} understated scope item(s)")
        if gaps:
            drivers.append(f"{len(gaps)} staffing gap(s)")
        if off_pref:
            drivers.append(f"{len(off_pref)} off-preference tech choice(s)")
        basis = " and ".join(drivers) if drivers else "the open items above"
        lines.append(
            f"_The +{contract.contingency_pct:.0f}% contingency in the estimate is justified by {basis}, "
            "not a flat habit._"
        )
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Research & Prior Art — deterministic render of the research dossier. This is
# the section that answers "did anyone try this before / what libraries exist /
# what are the real limits", with every row citing a consulted source.
# ---------------------------------------------------------------------------

_FINDING_KIND_LABEL = {
    "capability": "Capabilities & feasibility",
    "limit": "Service & tool limits",
    "gotcha": "Production gotchas",
    "benchmark": "Cost / effort benchmarks",
}


def _research_section(dossier: Optional[ResearchDossier]) -> str:
    if dossier is None:
        return ""
    if not (dossier.findings or dossier.prior_art or dossier.libraries or dossier.unanswered):
        return ""
    lines = ["## Research & Prior Art", ""]
    lines.append(
        f"_Compiled by iterative web research for this engagement: {dossier.sources_consulted} "
        f"sources across {dossier.queries_run} searches. Every entry links its source._"
    )
    lines.append("")

    if dossier.prior_art:
        lines.append("### Has anyone done this before?")
        lines.append("")
        lines.append("| Who | What they did | Outcome | Applies here? | Source |")
        lines.append("|-----|---------------|---------|---------------|--------|")
        for p in dossier.prior_art:
            lines.append(
                f"| {_md_cell(p.name)} | {_md_cell(p.what_they_did)} | {_md_cell(p.outcome)} "
                f"| {_md_cell(p.applicability)} | [source]({p.url}) |"
            )
        lines.append("")

    if dossier.libraries:
        lines.append("### Existing libraries & tools")
        lines.append("")
        lines.append("| Library / Tool | Covers | Maturity | Source |")
        lines.append("|----------------|--------|----------|--------|")
        for lib in dossier.libraries:
            lines.append(
                f"| {_md_cell(lib.name)} | {_md_cell(lib.purpose)} | {_md_cell(lib.maturity_note)} "
                f"| [source]({lib.url}) |"
            )
        lines.append("")

    # Findings grouped by kind, prior_art/library kinds excluded (tables above own them).
    grouped: dict[str, list] = {}
    for f in dossier.findings:
        if f.kind in ("prior_art", "library"):
            continue
        grouped.setdefault(f.kind, []).append(f)
    for kind in ("capability", "limit", "gotcha", "benchmark"):
        items = grouped.pop(kind, [])
        if not items:
            continue
        lines.append(f"### {_FINDING_KIND_LABEL[kind]}")
        lines.append("")
        for f in items:
            quote = f' — “{f.quote}”' if f.quote else ""
            title = f.source_title or "source"
            lines.append(f"- {f.claim}{quote} ([{_md_cell(title)}]({f.source_url}))")
        lines.append("")
    # Any non-standard kinds the model emitted still render rather than vanish.
    for kind, items in grouped.items():
        lines.append(f"### {kind.capitalize()}")
        lines.append("")
        for f in items:
            lines.append(f"- {f.claim} ([{_md_cell(f.source_title or 'source')}]({f.source_url}))")
        lines.append("")

    if dossier.unanswered:
        lines.append("### What research could not settle")
        lines.append("")
        for u in dossier.unanswered:
            lines.append(f"- {u}")
        lines.append("")
    return "\n".join(lines)


def _confidence_notes_block(notes: list[str]) -> str:
    """Honest-gaps surface: deterministic pipeline findings (research gaps, wide
    estimate bands, hedged verdicts). Surfaced gaps are the trust signal."""
    if not notes:
        return ""
    lines = ["## Confidence Notes", ""]
    lines.append("_Generated mechanically by the pipeline's validators — these are the places where this report's grounding is weakest. Resolve them before treating the affected numbers as commitments._")
    lines.append("")
    for n in notes:
        lines.append(f"- {n}")
    lines.append("")
    return "\n".join(lines)


def _approaches_block(approaches: list[ApproachOption]) -> str:
    if not approaches:
        return ""
    lines = ["## Approaches Considered", ""]
    # Recommended first, so the lead is the answer; then the alternatives.
    ordered = sorted(approaches, key=lambda a: (not a.recommended))
    for a in ordered:
        tag = " — **Recommended**" if a.recommended else ""
        lines.append(f"### {a.name}{tag}")
        lines.append("")
        if a.summary:
            lines.append(a.summary)
            lines.append("")
        if a.how_it_works:
            lines.append("**How it works:** " + a.how_it_works.strip())
            lines.append("")
        if a.best_when:
            lines.append(f"**Best when:** {a.best_when}")
        if a.tradeoffs:
            lines.append("**Tradeoffs:**")
            for t in a.tradeoffs:
                lines.append(f"- {t}")
        meta = f"_Risk: {a.risk_level} · Confidence: {a.confidence}_"
        lines.append(meta)
        if a.sources:
            srcs = ", ".join(f"[source]({u})" for u in a.sources if u)
            if srcs:
                lines.append(f"_Sources: {srcs}_")
        lines.append("")
    return "\n".join(lines)


# The cost block runs from its heading to the next ##/### heading (or EOF). Used
# to surgically re-render the cost table after a manual edit without re-running
# the whole pipeline — the section bodies aren't persisted, but the cost table is
# fully deterministic from the contract, so we can regenerate just this block.
_COST_TABLE_RE = re.compile(r"^### Cost & Effort Estimate\b.*?(?=^#{2,3} |\Z)", re.MULTILINE | re.DOTALL)


def rerender_cost_table(
    report_markdown: str,
    cost_lines: list[CostLine],
    cost_sensitivity: list[Sensitivity],
    contingency_pct: float,
) -> tuple[str, bool]:
    """Replace the '### Cost & Effort Estimate' block in an existing report with a
    freshly-rendered one (deterministic, LLM-free). Returns (new_markdown, replaced).

    `replaced=False` means the anchor heading wasn't found (legacy report / cost
    table rendered under a different section) — the caller keeps the contract edit
    but the markdown is left untouched."""
    new_block = _cost_table(compute_cost(cost_lines, cost_sensitivity, contingency_pct)).rstrip() + "\n\n"
    new_md, n = _COST_TABLE_RE.subn(lambda _m: new_block, report_markdown, count=1)
    return new_md, n > 0


def render_report(
    contract: ReportContract,
    sections_md: dict[str, str],
    judge_notes: Optional[dict[str, str]] = None,
) -> str:
    """Render the final report markdown.

    Args:
        contract: the planner's report contract.
        sections_md: {section.id: markdown body}. Every contract section must be present.
        judge_notes: optional {section.id: note}. Appended as an HTML comment so it
            survives round-trips but does not render to readers — useful when debugging
            a section the judge revised.

    Raises:
        KeyError: if any contract section is missing from sections_md.
    """
    missing = [s.id for s in contract.sections if s.id not in sections_md]
    if missing:
        raise KeyError(f"stitcher: sections_md missing required ids: {missing}")

    parts: list[str] = []

    parts.append(f"# {contract.report_title}\n")

    # Lead with the recommendation (Minto answer-first): commit-line, headline
    # numbers, and the verdict — so the report opens with direction, not prose.
    parts.append(_bottom_line_block(contract))

    # The engagement story up front: the problem, what we asked, what they told us.
    parts.append(_engagement_brief_block(contract))

    # What KIND of problem this is — the typed diagnosis the rest keys off.
    parts.append(_problem_shape_block(contract.problem_profile))

    # The crux and the 2-3 real approaches to it — the spine of a specialist's answer.
    parts.append(_core_challenge_block(contract.core_challenge))
    parts.append(_approaches_block(contract.approaches))

    # Stated vs. likely-actual — the two-sided expectation-gap corrector.
    parts.append(_reality_gap_section(contract))

    # What the world already knows: prior art, libraries, limits, benchmarks.
    parts.append(_research_section(contract.research_dossier))

    if contract.global_assumptions:
        parts.append(_global_assumptions_block(contract.global_assumptions))

    rendered_section_ids: set[str] = set()
    for section in contract.sections:
        body = sections_md[section.id]
        if judge_notes and section.id in judge_notes:
            body = f"{body.rstrip()}\n\n<!-- judge: {judge_notes[section.id]} -->"
        parts.append(_section_block(heading_level=2, title=section.title, body_md=body))
        # Attach deterministic decision tables right after their anchor section's prose.
        parts.extend(_tables_for_section(contract, section.id))
        rendered_section_ids.add(section.id)

    # Fallback: render decision tables whose anchor section the planner omitted.
    parts.append(_orphan_decision_blocks(contract, rendered_section_ids))

    if contract.known_issues:
        parts.append(_known_issues_section(contract.known_issues))

    if contract.open_questions_for_client:
        parts.append(_open_questions_block(contract.open_questions_for_client))

    # Honest gaps last — where the report's own grounding is weakest.
    parts.append(_confidence_notes_block(contract.confidence_notes))

    return "\n".join(p for p in parts if p)
