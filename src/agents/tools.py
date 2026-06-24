"""Deterministic helpers used by the contract pipeline.

These are *tools* the pipeline calls directly — not LLM-decided tool calls.
The original 8-agent pipeline did "evidence reasoning" and "mermaid review" as
LLM stages; here they are pure functions wherever the work is mechanically
checkable. The judge LLM only handles what genuinely needs judgment.

Add a new tool here when:
- It is deterministic (a pure function or a deterministic DB / vector lookup), AND
- An LLM stage would otherwise re-derive the same answer every time.

Do NOT add an LLM-wrapping helper here. Those belong in contract_workflow.py.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from typing import Optional


_MERMAID_BLOCK_RE = re.compile(r"```mermaid\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)

# A small set of diagram types we actually use in reports. Anything outside
# this list is suspicious — most likely the writer fabricated a syntax.
_KNOWN_DIAGRAM_HEADERS = (
    "graph",
    "flowchart",
    "sequenceDiagram",
    "classDiagram",
    "stateDiagram",
    "stateDiagram-v2",
    "erDiagram",
    "gantt",
    "pie",
    "journey",
    "C4Context",
)


@dataclass(frozen=True)
class MermaidIssue:
    section_id: str
    block_index: int  # which mermaid block within the section (0-based)
    message: str


def _validate_one_block(body: str) -> list[str]:
    """Return a list of issues for a single ```mermaid block body (text between fences).

    Lightweight checks only — we are not running a real mermaid parser. The goal
    is to catch the failure modes LLMs actually produce: empty diagrams, missing
    type header, unbalanced brackets, no edges in a flowchart.
    """
    issues: list[str] = []
    stripped = body.strip()
    if not stripped:
        return ["empty mermaid block"]

    first_word = stripped.split(None, 1)[0]
    if not any(first_word.startswith(h) for h in _KNOWN_DIAGRAM_HEADERS):
        issues.append(f"unrecognized diagram type '{first_word}' — expected one of {_KNOWN_DIAGRAM_HEADERS[:4]}…")

    # Balanced brackets — common LLM failure when copying complex labels.
    for opener, closer in (("[", "]"), ("(", ")"), ("{", "}")):
        if stripped.count(opener) != stripped.count(closer):
            issues.append(f"unbalanced '{opener}{closer}' brackets")

    # Flowchart / graph must have at least one edge declaration. A node-only
    # diagram is usually a sign the LLM gave up halfway.
    if first_word.startswith(("graph", "flowchart")):
        if not re.search(r"--?>|---|==>|-\.->", stripped):
            issues.append("flowchart has no edges — every node-only diagram is rejected")

    # SequenceDiagram needs at least one arrow.
    if first_word.startswith("sequenceDiagram"):
        if not re.search(r"->>|-->>|->|-->", stripped):
            issues.append("sequenceDiagram has no message arrows")

    return issues


def validate_mermaid(section_id: str, markdown: str) -> list[MermaidIssue]:
    """Scan a section's markdown for ```mermaid blocks; return a list of issues.

    Empty result means every block looks well-formed enough to render.
    """
    issues: list[MermaidIssue] = []
    for i, match in enumerate(_MERMAID_BLOCK_RE.finditer(markdown)):
        body = match.group(1)
        for msg in _validate_one_block(body):
            issues.append(MermaidIssue(section_id=section_id, block_index=i, message=msg))
    return issues


def format_mermaid_issues_for_judge(issues: list[MermaidIssue]) -> str:
    """Compact bullet list the judge prompt can append to its context.

    Returns empty string when there are no issues — caller can branch on truthy.
    """
    if not issues:
        return ""
    by_section: dict[str, list[str]] = {}
    for issue in issues:
        by_section.setdefault(issue.section_id, []).append(
            f"  - block #{issue.block_index}: {issue.message}"
        )
    lines = ["MERMAID VALIDATION ISSUES (treat as automatic rubric failure for mermaid_validity):"]
    for sid, msgs in by_section.items():
        lines.append(f"- section `{sid}`:")
        lines.extend(msgs)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Deterministic mermaid repair — runs on the final report markdown so what we
# persist (and the client renders) is valid mermaid even when the writer LLM
# leaves special characters unquoted. The #1 real-world failure is parentheses
# or slashes inside flowchart/subgraph node labels (`A[Foo (bar)]`), which
# mermaid rejects unless the label is wrapped in double quotes. We only ADD
# quotes — content is never dropped — so the pass is idempotent and safe to run
# on already-valid diagrams. Mirror of the frontend `repairMermaid()` so the two
# layers agree; the frontend keeps its copy as a last-line render-time fallback.
# ---------------------------------------------------------------------------

_MERMAID_FENCE_RE = re.compile(r"(```mermaid[ \t]*\n)(.*?)(```)", re.DOTALL | re.IGNORECASE)
# `id[...]` single-bracket labels (rectangles + subgraph titles). The negated
# class keeps each match inside one node and skips the doubled-bracket shapes,
# so we never corrupt `[[ ]]` / `[( )]`.
_FLOWCHART_LABEL_RE = re.compile(r"([A-Za-z0-9_]+)\[([^\[\]\n]+)\]")
# Pipe edge-labels, e.g. `A -->|some text| B`. The edge-label tokenizer rejects
# bare parens/brackets/braces/semicolons, so those get quoted.
_FLOWCHART_EDGE_LABEL_RE = re.compile(r"\|([^|\n]+)\|")
_EDGE_LABEL_RISKY_RE = re.compile(r"[()\[\]{};]")
_SEQ_ALIAS_RE = re.compile(
    r"^(\s*(?:participant|actor)\s+\S+\s+as\s+)(.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
# Flowchart-style participant labels — `participant S["Scheduler, daily…"]` or
# `participant S[Scheduler]` — are invalid in a sequenceDiagram: the parser wants
# `participant S` / `participant S as <name>` and rejects the `[` (the real-world
# "Expecting 'ACTOR', got 'INVALID'" failure). The LLM borrowed flowchart node
# syntax. Capture id + bracket label so we can rewrite to a quoted `as` alias.
_SEQ_PARTICIPANT_BRACKET_RE = re.compile(
    r"^(\s*(?:participant|actor)\s+)([A-Za-z0-9_]+)\s*\[\s*(.+?)\s*\]\s*$",
    re.IGNORECASE | re.MULTILINE,
)
# Inside a sequenceDiagram, actors are *referenced* in message / Note / activate
# lines with the same bad flowchart shape, e.g. `S["Scheduler"] ->> W["Worker"]: hi`.
# The parser rejects the `[` after an actor too (`Expecting '…ARROW…', got ','`).
# Once the participant declarations carry the label via `as`, these inline labels
# are pure noise — strip every `id[…]` down to the bare id so the messages parse.
_SEQ_ACTOR_BRACKET_RE = re.compile(r"([A-Za-z0-9_]+)\[[^\]\n]*\]")


def _quote_mermaid_label(label: str) -> str:
    stripped = label.strip()
    if len(stripped) >= 2 and stripped.startswith('"') and stripped.endswith('"'):
        return label  # already quoted — leave as-is (idempotent)
    return '"' + stripped.replace('"', "#quot;") + '"'


def _quote_edge_label(m: "re.Match[str]") -> str:
    t = m.group(1).strip()
    if len(t) >= 2 and t.startswith('"') and t.endswith('"'):
        return m.group(0)
    if _EDGE_LABEL_RISKY_RE.search(t):
        return f"|{_quote_mermaid_label(t)}|"
    return m.group(0)


def _replace_seq_semicolons(line: str) -> str:
    # `;` is a statement separator in mermaid; LLMs use it as punctuation inside
    # message text, which truncates the message. Replace `;` after the first
    # `:` (the message body) with `,`.
    idx = line.find(":")
    return line if idx == -1 else line[: idx + 1] + line[idx + 1:].replace(";", ",")


def _repair_one_mermaid_block(body: str) -> str:
    head = body.lstrip().split("\n", 1)[0].strip()
    if re.match(r"^(graph|flowchart)\b", head, re.IGNORECASE):
        out = _FLOWCHART_LABEL_RE.sub(
            lambda m: f"{m.group(1)}[{_quote_mermaid_label(m.group(2))}]", body
        )
        return _FLOWCHART_EDGE_LABEL_RE.sub(_quote_edge_label, out)
    if head.startswith("sequenceDiagram"):
        # 1) Declarations: `participant S[...]` -> `participant S as "..."`. Must
        #    run before the strip below so the label is preserved as the alias.
        out = _SEQ_PARTICIPANT_BRACKET_RE.sub(
            lambda m: f"{m.group(1)}{m.group(2)} as {_quote_mermaid_label(m.group(3))}", body
        )
        # 2) Strip the bracket label off every remaining inline actor reference
        #    (message / Note / activate lines). Declarations were rewritten in (1),
        #    so this only touches refs; the declared `as` alias keeps the name.
        out = _SEQ_ACTOR_BRACKET_RE.sub(lambda m: m.group(1), out)
        # 3) Quote any bare `as` aliases (idempotent: (1) already emits quoted ones).
        out = _SEQ_ALIAS_RE.sub(
            lambda m: f"{m.group(1)}{_quote_mermaid_label(m.group(2))}", out
        )
        return "\n".join(_replace_seq_semicolons(ln) for ln in out.split("\n"))
    return body


def repair_mermaid_blocks(markdown: str) -> str:
    """Quote risky labels inside every ```mermaid block so the diagram renders.

    Deterministic and idempotent. Returns the input unchanged when it contains
    no mermaid fences. See module-level comment for the failure mode this fixes.
    """
    if not markdown or "```mermaid" not in markdown:
        return markdown
    return _MERMAID_FENCE_RE.sub(
        lambda m: m.group(1) + _repair_one_mermaid_block(m.group(2)) + m.group(3),
        markdown,
    )


# ---------------------------------------------------------------------------
# Citation enforcement — the audit trail is the whole point of the Contract, so
# a quantitative claim that is neither linked nor labeled an assumption is a
# mechanical failure, not a stylistic note. Same precheck → judge pattern as
# mermaid. We deliberately check only money and percentage figures (the claims
# clients challenge first) to keep false positives low.
# ---------------------------------------------------------------------------

# Money ($1,200 / $1.2) or a percentage (30% / 12.5 %).
_NUMERIC_CLAIM_RE = re.compile(r"\$\s?[\d,]+(?:\.\d+)?|\b\d+(?:\.\d+)?\s?%")
# A *valid* citation link: a real http(s) URL or a real internal anchor. This
# deliberately rejects placeholder links the writers fall back to when they have
# nothing to cite — `[x](#)`, `[x](undefined)`, `[Confirmed Q&A (quoted)](#)` —
# which is exactly the opaque-citation failure mode we are stamping out.
_MD_LINK_RE = re.compile(r"\[[^\]]+\]\((?:https?://[^)\s]+|#[\w-]+)\)")

# Phrases that count as a valid in-prose basis even without a markdown link:
# an explicit assumption, a reference to the firm rate card the cost lines cite,
# or a plain-prose reference to the client's own document (the citation model is:
# client-doc facts are stated in prose, external/industry facts get a real link).
_BASIS_CUES = (
    "assumption",
    "rate card", "rate-card",
    # Explicit plain-prose references to the client's own document. Deliberately
    # specific — generic words like "q&a" or "client" are NOT cues, because an
    # opaque label like "(Confirmed Q&A (quoted))" must still be rejected.
    "per the rfp", "the rfp", "per the brief", "the brief", "per the document", "the document",
)


@dataclass(frozen=True)
class CitationIssue:
    section_id: str
    claim: str
    message: str


def validate_citations(section_id: str, markdown: str, window: int = 160) -> list[CitationIssue]:
    """Flag money/percentage claims not within `window` chars of a markdown link
    or a labeled-assumption / rate-card basis.

    Empty result means every quantitative claim in the section is grounded.
    """
    issues: list[CitationIssue] = []
    link_spans = [m.span() for m in _MD_LINK_RE.finditer(markdown)]
    lowered = markdown.lower()

    for m in _NUMERIC_CLAIM_RE.finditer(markdown):
        start, end = m.span()
        lo = max(0, start - window)
        hi = min(len(markdown), end + window)
        near_link = any(not (ls >= hi or le <= lo) for ls, le in link_spans)
        near_basis = any(cue in lowered[lo:hi] for cue in _BASIS_CUES)
        if not (near_link or near_basis):
            issues.append(CitationIssue(
                section_id=section_id,
                claim=m.group(0).strip(),
                message="quantitative claim not near a citation link or labeled assumption/rate-card basis",
            ))
    return issues


def format_prechecks_for_judge(
    mermaid_issues: list[MermaidIssue],
    citation_issues: list[CitationIssue],
    contract_issues: list["ContractIssue"] | None = None,
) -> str:
    """Merge all deterministic precheck failures into one block for the judge.

    Returns "(none — all deterministic checks passed)" when both are empty so the
    judge prompt always has a concrete value to interpolate.
    """
    parts: list[str] = []
    mermaid_block = format_mermaid_issues_for_judge(mermaid_issues)
    if mermaid_block:
        parts.append(mermaid_block)

    if citation_issues:
        by_section: dict[str, list[str]] = {}
        for issue in citation_issues:
            by_section.setdefault(issue.section_id, []).append(
                f"  - uncited claim '{issue.claim}': {issue.message}"
            )
        lines = ["CITATION ISSUES (treat as automatic rubric failure for citation_completeness):"]
        for sid, msgs in by_section.items():
            lines.append(f"- section `{sid}`:")
            lines.extend(msgs)
        parts.append("\n".join(lines))

    if contract_issues:
        lines = [
            "CONTRACT-LEVEL ISSUES (decider-level — do NOT ask a section writer to fix these; "
            "they are already recorded as Confidence Notes. Reflect them in overall_quality_score "
            "and do not let prose paper over them):"
        ]
        for ci in contract_issues:
            lines.append(f"- [{ci.area}] {ci.message}")
        parts.append("\n".join(lines))

    return "\n\n".join(parts) if parts else "(none — all deterministic checks passed)"


# ---------------------------------------------------------------------------
# Contract-level validators — mechanical enforcement of rules the decide prompt
# states but a model can quietly ignore (band discipline, verdict discipline,
# staffing-gap consistency, research coverage). Same precheck → judge pattern,
# but these are DECIDER-level: a writer cannot fix a 3x estimate band with prose,
# so the issues surface as Confidence Notes instead of writer revisions.
# ---------------------------------------------------------------------------

# hours_high / hours_low above this is a refusal to estimate, not an estimate
# (the decide prompt asks for ≤ ~1.4×; the validator allows a little slack).
MAX_HOURS_BAND_RATIO = 1.45
# A go-with-conditions verdict hedged behind more conditions than this reads as
# "no opinion" (the decide prompt caps at 1-3).
MAX_VERDICT_CONDITIONS = 3
# A research query whose findings fall below this is a research gap — related
# claims are ungrounded and must be treated as assumptions.
MIN_RESEARCH_RESULTS_PER_QUERY = 2


@dataclass(frozen=True)
class ContractIssue:
    area: str  # "cost" | "verdict" | "research"
    message: str


def validate_cost_bands(cost_lines, max_ratio: float = MAX_HOURS_BAND_RATIO) -> list[ContractIssue]:
    """Flag cost lines whose hours band exceeds the discipline ratio.

    Accepts CostLine models or plain dicts (the contract is stored as JSON)."""
    issues: list[ContractIssue] = []
    for cl in cost_lines or []:
        low = getattr(cl, "hours_low", None) if not isinstance(cl, dict) else cl.get("hours_low")
        high = getattr(cl, "hours_high", None) if not isinstance(cl, dict) else cl.get("hours_high")
        workstream = getattr(cl, "workstream", "") if not isinstance(cl, dict) else cl.get("workstream", "")
        role = getattr(cl, "role", "") if not isinstance(cl, dict) else cl.get("role", "")
        if not low or high is None:
            continue
        ratio = high / low if low else float("inf")
        if ratio > max_ratio:
            issues.append(ContractIssue(
                area="cost",
                message=(
                    f"estimate band for '{workstream} / {role}' is {low}–{high}h "
                    f"({ratio:.1f}x > {max_ratio}x) — scope is not understood well enough to "
                    "estimate; treat as low-confidence until the scope question is resolved"
                ),
            ))
    return issues


def validate_verdict_discipline(
    feasibility, max_conditions: int = MAX_VERDICT_CONDITIONS,
) -> list[ContractIssue]:
    """Flag a go-with-conditions verdict hedged behind a wishlist of conditions."""
    if feasibility is None:
        return []
    verdict = getattr(feasibility, "verdict", None) if not isinstance(feasibility, dict) else feasibility.get("verdict")
    conditions = getattr(feasibility, "conditions", None) if not isinstance(feasibility, dict) else feasibility.get("conditions")
    conditions = conditions or []
    if verdict == "go-with-conditions" and len(conditions) > max_conditions:
        return [ContractIssue(
            area="verdict",
            message=(
                f"'go-with-conditions' carries {len(conditions)} conditions (max {max_conditions}) — "
                "this reads as no opinion; the verdict is effectively unsettled"
            ),
        )]
    return []


def research_gaps(
    queries: list[str],
    findings: list[dict],
    min_results: int = MIN_RESEARCH_RESULTS_PER_QUERY,
) -> list[str]:
    """Return the research queries that came back with too little evidence.

    Pure post-hoc check over the findings pool (each finding carries the `query`
    it answered), so research_node's signature stays untouched."""
    counts: dict[str, int] = {}
    for f in findings or []:
        q = (f or {}).get("query")
        if q:
            counts[q] = counts.get(q, 0) + 1
    return [q for q in (queries or []) if q and counts.get(q, 0) < min_results]


def dossier_source_urls(dossier) -> set[str]:
    """All URLs the research dossier actually consulted — the only URLs any
    downstream artifact may cite."""
    urls: set[str] = set()
    if not dossier:
        return urls
    for f in getattr(dossier, "findings", []) or []:
        if getattr(f, "source_url", ""):
            urls.add(f.source_url)
    for p in getattr(dossier, "prior_art", []) or []:
        if getattr(p, "url", ""):
            urls.add(p.url)
    for lib in getattr(dossier, "libraries", []) or []:
        if getattr(lib, "url", ""):
            urls.add(lib.url)
    return urls


def sanitize_service_option_sources(contract) -> int:
    """Blank any service_option.source_url not present in the dossier's sources
    (or every one, when there is no dossier) — the decider may only cite research
    it was actually given. Mutates in place; returns how many were blanked."""
    allowed = dossier_source_urls(getattr(contract, "research_dossier", None))
    blanked = 0
    for td in contract.tech_decisions or []:
        for opt in td.service_options or []:
            if opt.source_url and opt.source_url not in allowed:
                opt.source_url = ""
                blanked += 1
    return blanked


# ---------------------------------------------------------------------------
# Firm rate-card grounding — the cost table is the report's most-challenged
# number, so the $/hr is the firm's own rate, never the model's guess. The
# writer/decider emit role + hours; this overwrites rate_usd from the firm rate
# card and stamps the rate_card_ref for defensibility. A role the card doesn't
# cover keeps its market estimate and surfaces as a Confidence Note (honest gap,
# not a silent wrong number). No-op when the firm has no rate card — today's
# behavior, the model's estimate stands.
# ---------------------------------------------------------------------------

# Below this fuzzy role-match ratio we treat the role as absent from the rate
# card rather than risk pricing a line off an unrelated role. Mirrors the
# question-dedupe threshold (database_scripts._is_duplicate_question).
MIN_RATE_MATCH_RATIO = 0.72


def _norm_role(s) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _match_rate_row(role: str, seniority: str, rate_cards: list[dict]) -> Optional[dict]:
    """Best firm rate-card row for a (role, seniority): exact role + seniority,
    then exact role (any seniority), then a fuzzy role match. None if nothing
    clears the fuzzy threshold."""
    if not rate_cards:
        return None
    nrole, nsen = _norm_role(role), _norm_role(seniority)

    role_matches = [rc for rc in rate_cards if _norm_role(rc.get("role")) == nrole]
    if role_matches:
        for rc in role_matches:
            if _norm_role(rc.get("seniority")) == nsen:
                return rc
        return role_matches[0]

    best, best_ratio = None, 0.0
    for rc in rate_cards:
        ratio = difflib.SequenceMatcher(None, nrole, _norm_role(rc.get("role"))).ratio()
        if ratio > best_ratio:
            best, best_ratio = rc, ratio
    return best if best_ratio >= MIN_RATE_MATCH_RATIO else None


def resolve_rates(cost_lines, rate_cards: list[dict]) -> list[str]:
    """Overwrite each cost line's hourly rate with the firm's rate-card rate.

    Deterministic — the model only supplies role + hours; the firm's real $/hr is
    never left to it. Mutates CostLine instances in place; returns Confidence
    Notes for any role the rate card does not cover (its estimate is kept). No-op
    when the firm has no rate card on file.
    """
    notes: list[str] = []
    if not rate_cards or not cost_lines:
        return notes

    unmatched: dict[str, float] = {}  # role label -> kept estimate (dedupes notes)
    for cl in cost_lines:
        role = getattr(cl, "role", "") or ""
        seniority = getattr(cl, "seniority", "") or ""
        row = _match_rate_row(role, seniority, rate_cards)
        if row and isinstance(row.get("hourly_rate_usd"), (int, float)):
            cl.rate_usd = float(row["hourly_rate_usd"])
            label = f"{row.get('role', '')}/{row.get('seniority', '')}".strip("/")
            cl.rate_card_ref = f"firm:{label} v{row.get('version', 1)}"
        else:
            label = role + (f" ({seniority})" if seniority else "")
            unmatched.setdefault(label, float(getattr(cl, "rate_usd", 0.0) or 0.0))

    for label, rate in unmatched.items():
        notes.append(
            f"Rate for '{label}' is not on your firm rate card — a market estimate of "
            f"${rate:,.0f}/hr was used. Add the role to your rate card for a firm-grounded number."
        )
    return notes


def reconcile_staffing_gaps(contract) -> int:
    """Deterministic firm-fit cross-check: every team role the decider marked
    `in_firm_roster=False` MUST have a staffing_gaps entry — don't trust the
    decider to remember. Appends missing entries in place; returns how many
    were added. Operates on a ReportContract instance."""
    from agents.contract import StaffingGap  # local import to avoid a cycle at module load

    covered = {
        (g.needed_role or "").strip().lower()
        for g in (contract.staffing_gaps or [])
    }
    added = 0
    for t in contract.team or []:
        if t.in_firm_roster is False and (t.role or "").strip().lower() not in covered:
            contract.staffing_gaps.append(StaffingGap(
                needed_role=t.role,
                covered_by_firm=False,
                recommendation="contract",
                impact="Role is not on the firm rate card — staffing plan (hire/contract/partner) needed before kickoff.",
            ))
            covered.add((t.role or "").strip().lower())
            added += 1
    return added
