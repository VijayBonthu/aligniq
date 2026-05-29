"""Report contract — the canonical artifact the new pipeline executes against.

The planner emits a ReportContract once per run. Section writers each consume
one ReportSection plus retrieved evidence. The stitcher (src/agents/stitcher.py)
renders the contract + written sections into final markdown without an LLM.

The contract is the moat: section-scoped regen, semantic diff, SOW generation,
inline citations all hang off this shape — none of them hang cleanly off the
old `req_analysis` list.
"""

from typing import Optional
from pydantic import BaseModel, Field


class ReportSection(BaseModel):
    id: str = Field(description="Stable slug; used as the section anchor and the dict key in sections_md.")
    title: str = Field(description="Human-readable section heading.")
    writer_brief: str = Field(description="1-2 paragraph instructions the writer agent executes against.")
    claims_to_make: list[str] = Field(
        default_factory=list,
        description="Specific claims the section must support, each citable to evidence or labeled as an assumption.",
    )
    evidence_pointers: list[str] = Field(
        default_factory=list,
        description="Chroma chunk ids the writer should retrieve to ground claims.",
    )
    rubric_focus: list[str] = Field(
        default_factory=list,
        description="Judge axes that matter most for this section (e.g. coverage, specificity, mermaid_validity).",
    )
    diagrams_required: list[str] = Field(
        default_factory=list,
        description="Mermaid diagram types this section must include (component, sequence, deployment).",
    )
    rate_card_required: bool = Field(
        default=False,
        description="If true, writer must look up firm rate-card lines and cite each cost number to a role/region row.",
    )


class OpenQuestion(BaseModel):
    """An ambiguity or gap the report cannot resolve from the document alone."""

    question: str
    why_it_matters: str
    severity: str = Field(description="blocker | high | medium | low")
    related_section_id: Optional[str] = Field(
        default=None,
        description="Section whose conclusions hinge on this answer; None if cross-cutting.",
    )


# ---------------------------------------------------------------------------
# Typed decision artifacts — populated by the `decide` stage, NOT the planner.
# The stitcher renders these deterministically (cost math is Python, never LLM);
# section writers receive them as input and write justification prose only.
# ---------------------------------------------------------------------------


class ServiceOption(BaseModel):
    """A concrete managed service or OSS project that implements a TechDecision,
    so the reader doesn't have to go find what to actually deploy."""

    provider: str = Field(description="aws | azure | gcp | oss | other")
    service: str = Field(description="The concrete service/project, e.g. 'Azure AI Search' or 'pgvector'.")
    note: str = Field(default="", description="One line: when to pick this, or managed-vs-self-hosted tradeoff.")


class TechDecision(BaseModel):
    """One recommended technology choice with the alternatives it beat."""

    layer: str = Field(description="frontend | backend | datastore | infra | auth | integration | ...")
    choice: str = Field(description="The recommended technology, e.g. 'React 19 + TypeScript'.")
    alternatives: list[str] = Field(default_factory=list, description="Options considered and rejected.")
    rationale: str = Field(description="Why this was chosen over the alternatives.")
    confidence: str = Field(description="high | medium | low")
    honors_firm_pref: bool = Field(
        default=True,
        description="True if the choice respects firm tech preferences and avoids blocked vendors.",
    )
    basis: str = Field(
        default="",
        description="Evidence link text grounding the choice, or 'Assumption: ...' when not grounded.",
    )
    service_options: list[ServiceOption] = Field(
        default_factory=list,
        description="Concrete cloud (aws/azure/gcp) + OSS services that implement this choice.",
    )


class CostLine(BaseModel):
    """One role's effort on one workstream. Totals are computed by the stitcher."""

    workstream: str = Field(description="Ties this cost line to a milestone / section of work.")
    role: str
    seniority: str = ""
    region: str = ""
    hours_low: int = Field(description="Low-end effort estimate in hours.")
    hours_high: int = Field(description="High-end effort estimate in hours.")
    rate_usd: float = Field(description="Hourly rate pulled from a firm rate-card row.")
    rate_card_ref: str = Field(
        default="",
        description="Which rate-card row the rate came from, e.g. 'BE engineer, senior, us-east'. For defensibility.",
    )


class Sensitivity(BaseModel):
    """A condition that shifts the cost estimate up or down."""

    condition: str = Field(description="e.g. 'if Salesforce integration is in scope'")
    delta_pct: float = Field(description="Percent change to the estimate, e.g. 30 or -15.")


class Milestone(BaseModel):
    """One phase of delivery on the roadmap."""

    name: str
    weeks_low: int = Field(description="Low-end duration in weeks.")
    weeks_high: int = Field(description="High-end duration in weeks.")
    depends_on: list[str] = Field(default_factory=list, description="Names of milestones this one depends on.")
    deliverables: list[str] = Field(default_factory=list)


class TeamRole(BaseModel):
    """One role's allocation on the engagement."""

    role: str
    seniority: str = ""
    fte: float = Field(description="Full-time-equivalent allocation, e.g. 0.5 or 2.0.")
    duration_weeks: int = Field(description="How many weeks this role is engaged.")
    in_firm_roster: Optional[bool] = Field(
        default=None,
        description="True if the firm's rate card staffs this role; False flags a staffing gap; None = unknown.",
    )


class StaffingGap(BaseModel):
    """A role the engagement needs that the firm's rate-card roster does not cover."""

    needed_role: str = Field(description="e.g. 'AI/ML Engineer'")
    covered_by_firm: bool = Field(description="False when no matching rate-card row exists.")
    recommendation: str = Field(description="hire | contract | upskill existing <role> | partner")
    impact: str = Field(description="Cost/timeline impact if the gap is unfilled.")


class KnownIssue(BaseModel):
    """A known pitfall in a recommended technology or integration, with a workaround
    and a real source link. Populated by the Tavily-backed known_issues stage."""

    area: str = Field(description="The tech or integration seam, e.g. 'Power BI embed <-> Azure Functions'.")
    issue: str = Field(description="What the known problem is.")
    symptom: str = Field(default="", description="The concrete error/behavior the team will hit.")
    workaround: str = Field(description="How to avoid or fix it.")
    source_url: str = Field(description="Clickable source URL — MUST come from a real search result.")
    severity: str = Field(default="medium", description="high | medium | low")
    confidence: str = Field(default="medium", description="high | medium | low")


class FeasibilityVerdict(BaseModel):
    """The headline go/no-go call. Preliminary at decide time; judge may flag contradictions."""

    verdict: str = Field(description="go | go-with-conditions | no-go")
    confidence: str = Field(description="high | medium | low")
    conditions: list[str] = Field(default_factory=list, description="Conditions attached to a go-with-conditions verdict.")
    risks_driving_verdict: list[str] = Field(default_factory=list)


class ReportContract(BaseModel):
    """The plan node emits this. Writers + judge + stitcher consume it."""

    report_title: str
    executive_summary_brief: str = Field(
        description="2-4 sentence summary the planner commits to up front; the executive_summary section writer expands this.",
    )
    sections: list[ReportSection]
    open_questions_for_client: list[OpenQuestion] = Field(default_factory=list)
    validated_requirements: dict = Field(
        default_factory=dict,
        description=(
            "Structured FRs/NFRs/constraints with priority and source. Replaces validator_agent output. "
            "Free-form dict (planner-shaped) — readers should not assume keys; treat as section-scoped input."
        ),
    )
    global_assumptions: list[str] = Field(
        default_factory=list,
        description="Cross-cutting assumptions every section inherits (e.g. 'AWS us-east-1 region', 'on-prem AD federated').",
    )

    # Decision artifacts — empty after the plan stage, filled by the decide stage.
    # The stitcher renders these as tables; writers reference them but never recompute.
    tech_decisions: list[TechDecision] = Field(default_factory=list)
    cost_lines: list[CostLine] = Field(default_factory=list)
    cost_sensitivity: list[Sensitivity] = Field(default_factory=list)
    contingency_pct: float = Field(
        default=0.0,
        description="Contingency buffer applied to cost totals by the stitcher, e.g. 15 for +15%.",
    )
    timeline: list[Milestone] = Field(default_factory=list)
    team: list[TeamRole] = Field(default_factory=list)
    feasibility: Optional[FeasibilityVerdict] = None

    # Slice-2 actionability fields — also filled by the decide stage (known_issues
    # by the Tavily sub-step). All optional; empty renders nothing.
    integration_points: list[str] = Field(
        default_factory=list,
        description="Cross-system seams in the proposed solution; drives the known-issues research queries.",
    )
    staffing_gaps: list[StaffingGap] = Field(default_factory=list)
    known_issues: list[KnownIssue] = Field(default_factory=list)

    def section_ids(self) -> list[str]:
        return [s.id for s in self.sections]

    def get_section(self, section_id: str) -> Optional[ReportSection]:
        for s in self.sections:
            if s.id == section_id:
                return s
        return None
