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

import re
from dataclasses import dataclass


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
        out = _SEQ_ALIAS_RE.sub(
            lambda m: f"{m.group(1)}{_quote_mermaid_label(m.group(2))}", body
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
_MD_LINK_RE = re.compile(r"\[[^\]]+\]\([^)]+\)")

# Phrases that count as a valid in-prose basis even without a markdown link:
# an explicit assumption, or a reference to the firm rate card the cost lines cite.
_BASIS_CUES = ("assumption", "rate card", "rate-card")


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

    return "\n\n".join(parts) if parts else "(none — all deterministic checks passed)"
