"""
Report section parser for the Deliverable Builder (A5).

Parses a markdown report (as produced by Report_Generator_Prompt) into a flat,
ordered list of Sections at H2 + H3 granularity. Section IDs are derived
deterministically from the numeric heading prefix the prompt enforces
(e.g. "### 3.2 Unanswered Questions" -> "s-3-2-unanswered-questions"), so
they are stable across regenerations as long as the prompt's section
numbering does not change.

Each section is classified as 'internal' or 'standard'. Internal sections
default to excluded in a fresh deliverable; the user can override per row
in the builder UI.

Pre-mortem content lives in report_version.pre_mortem (separate JSON column)
and is intentionally NOT surfaced as a Section here — the Pre-Mortem panel
stays in ChatView and never appears in the client deliverable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Iterator, List, Optional


# Matches H2/H3 headings, with or without a numeric prefix:
#   `## 3. Title` / `### 3.2 Title` (legacy Report_Generator_Prompt), AND
#   `## Title` / `### Title` (contract pipeline stitcher — un-numbered).
# Group 1 = hash prefix (## or ###), Group 2 = dotted number (optional),
# Group 3 = title. The numeric group is non-greedy and only matches a leading
# run of digits/dots followed by whitespace, so plain titles never lose words.
_HEADING_RE = re.compile(r"^(#{2,3})\s+(?:([\d.]+?)\.?\s+)?(.+?)\s*$")

# Heading text patterns that mark internal-only content. These are belt-and-
# suspenders fallbacks; the numeric rules below cover the prompt-enforced
# headings, and the text rules cover prompt drift.
_INTERNAL_TEXT_PATTERNS = [
    re.compile(r"unanswered\s+question", re.I),
    re.compile(r"open\s+question", re.I),
    re.compile(r"candidate\s+architectur", re.I),
    re.compile(r"alternative\s+architectur", re.I),
    re.compile(r"\bmvp\s+effort\b", re.I),
    re.compile(r"\bproduction\s+effort\b", re.I),
    re.compile(r"effort\s+breakdown", re.I),
    re.compile(r"staffing", re.I),
    re.compile(r"rate\s+card", re.I),
]

# Numeric section-number rules that mark internal-only content.
# Keyed by exact dotted number from the prompt structure.
_INTERNAL_NUMBERS = {
    "3.2",   # Unanswered Questions
    "4.1",   # Candidate Architectures (alternatives)
    "6.1",   # MVP Effort Breakdown (staffing)
    "6.2",   # Production Effort Breakdown (staffing)
}


@dataclass
class Section:
    """A parsed section of the report.

    Attributes:
        id: Stable identifier, e.g. "s-3-2-unanswered-questions".
        heading_level: 2 for H2, 3 for H3.
        heading_number: Dotted number from the prompt, e.g. "3.2". Empty if
            the heading lacks a numeric prefix.
        heading_text: Title text without the number, e.g. "Unanswered Questions".
        parent_id: For H3 sections, the id of the enclosing H2. None for H2.
        raw_markdown: The section's markdown including its own heading line,
            up to (but not including) the next same-or-higher heading.
        kind: 'internal' (default-excluded) or 'standard' (default-included).
    """
    id: str
    heading_level: int
    heading_number: str
    heading_text: str
    parent_id: Optional[str]
    raw_markdown: str
    kind: str  # 'internal' | 'standard'

    def to_dict(self) -> dict:
        return asdict(self)


def _slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s or "section"


def _make_id(number: str, title: str) -> str:
    if number:
        num_part = number.replace(".", "-")
        return f"s-{num_part}-{_slugify(title)}"
    return f"s-{_slugify(title)}"


def _classify(number: str, title: str) -> str:
    if number in _INTERNAL_NUMBERS:
        return "internal"
    for pat in _INTERNAL_TEXT_PATTERNS:
        if pat.search(title):
            return "internal"
    return "standard"


def _iter_heading_lines(markdown: str) -> Iterator[tuple[int, int, str, str]]:
    """Yield (line_index, heading_level, number, title) for every H2/H3 in order."""
    for idx, line in enumerate(markdown.splitlines()):
        m = _HEADING_RE.match(line)
        if not m:
            continue
        level = len(m.group(1))  # ## -> 2, ### -> 3
        number = m.group(2) or ""  # "" when the heading carries no numeric prefix
        title = m.group(3).strip()
        yield idx, level, number, title


def parse_sections(report_markdown: str) -> List[Section]:
    """Parse a markdown report into an ordered list of Sections.

    Sections cover H2 and H3 headings only. Each section's raw_markdown
    spans from its own heading line up to (but not including) the next
    heading at the same or higher level. Returns an empty list for empty
    or heading-less input.
    """
    if not report_markdown or not report_markdown.strip():
        return []

    lines = report_markdown.splitlines()
    headings = list(_iter_heading_lines(report_markdown))
    if not headings:
        return []

    sections: List[Section] = []
    current_h2_id: Optional[str] = None
    # Un-numbered headings derive their id from the title slug, which can
    # collide (e.g. two "### Overview"). Suffix duplicates so ids stay unique —
    # otherwise React keys clash and per-section edit/exclude state bleeds.
    seen_ids: dict[str, int] = {}

    for i, (line_idx, level, number, title) in enumerate(headings):
        # Each section's content ends at the NEXT heading of any level we
        # parse (H2 or H3). For an H2 with H3 children, this means the H2's
        # raw_markdown is just its heading + any prelude text before the
        # first H3 — the H3 children own their own bodies. Without this, the
        # H2 would duplicate every H3 inside it.
        end_idx = headings[i + 1][0] if i + 1 < len(headings) else len(lines)

        raw = "\n".join(lines[line_idx:end_idx]).rstrip() + "\n"
        base_id = _make_id(number, title)
        seen = seen_ids.get(base_id, 0)
        seen_ids[base_id] = seen + 1
        section_id = base_id if seen == 0 else f"{base_id}-{seen + 1}"
        kind = _classify(number, title)

        if level == 2:
            current_h2_id = section_id
            parent_id = None
        else:  # level == 3
            parent_id = current_h2_id

        sections.append(
            Section(
                id=section_id,
                heading_level=level,
                heading_number=number,
                heading_text=title,
                parent_id=parent_id,
                raw_markdown=raw,
                kind=kind,
            )
        )

    return sections


def assemble_deliverable(
    sections: List[Section],
    *,
    excluded_ids: set[str],
    section_edits: dict[str, str],
    polished: dict[str, dict],
    custom_sections: List[dict],
) -> str:
    """Assemble the final deliverable markdown from parsed sections + curation state.

    - Drops any section whose id is in excluded_ids.
    - For each remaining section, prefers polished[id].markdown, then
      section_edits[id], then the original raw_markdown.
    - Interleaves custom_sections at their `position.after_section_id` anchor.
      Custom sections whose anchor is excluded or unknown append at the end
      (defensive; the config endpoint should reject unknown anchors at write
      time).
    - When all H3 children of an H2 are excluded, the H2 heading is also
      dropped (no orphaned containers).
    """
    excluded = set(excluded_ids)

    # Determine which H2 containers to keep: keep an H2 if itself is not
    # excluded AND (it has no H3 children that survive OR at least one
    # H3 child survives). Simpler rule that matches user intent:
    # drop an H2 only when explicitly excluded OR when every H3 child is excluded.
    h2_ids_with_children: dict[str, list[str]] = {}
    for s in sections:
        if s.heading_level == 3 and s.parent_id:
            h2_ids_with_children.setdefault(s.parent_id, []).append(s.id)

    h2_to_drop: set[str] = set()
    for h2_id, child_ids in h2_ids_with_children.items():
        if all(cid in excluded for cid in child_ids):
            h2_to_drop.add(h2_id)

    # Group custom sections by anchor for interleaving.
    customs_by_anchor: dict[str, list[dict]] = {}
    for cs in custom_sections:
        anchor = (cs.get("position") or {}).get("after_section_id") or "__end__"
        customs_by_anchor.setdefault(anchor, []).append(cs)

    out_parts: List[str] = []

    for s in sections:
        if s.id in excluded:
            continue
        if s.heading_level == 2 and s.id in h2_to_drop:
            # Skip the orphaned H2 heading but still allow customs anchored
            # to it to appear (defensive).
            for cs in customs_by_anchor.pop(s.id, []):
                md = (cs.get("markdown") or "").rstrip() + "\n"
                if md.strip():
                    out_parts.append(md)
            continue

        if s.id in polished and polished[s.id].get("markdown"):
            out_parts.append(polished[s.id]["markdown"].rstrip() + "\n")
        elif s.id in section_edits and section_edits[s.id]:
            out_parts.append(section_edits[s.id].rstrip() + "\n")
        else:
            out_parts.append(s.raw_markdown)

        for cs in customs_by_anchor.pop(s.id, []):
            md = (cs.get("markdown") or "").rstrip() + "\n"
            if md.strip():
                out_parts.append(md)

    # Append any customs whose anchor was unknown or excluded.
    for anchor, cs_list in customs_by_anchor.items():
        for cs in cs_list:
            md = (cs.get("markdown") or "").rstrip() + "\n"
            if md.strip():
                out_parts.append(md)

    return "\n".join(out_parts).rstrip() + "\n"


def default_excluded_ids(sections: List[Section]) -> List[str]:
    """Section IDs that should default to excluded (kind == 'internal')."""
    return [s.id for s in sections if s.kind == "internal"]


# ---------------------------------------------------------------------------
# Fenced-block + diagram extraction, and friendly-name section lookup.
#
# These power the "report-as-wiki" chat retrieval (Tier 1): the chat agent
# serves whole sections and diagrams DETERMINISTICALLY from the stored report
# markdown instead of reassembling fuzzy vector fragments. The same fence
# splitter keeps mermaid/code blocks atomic during section-aware chunking
# (vectordb/chunking.py) so embeddings never shred a diagram again.
# ---------------------------------------------------------------------------

# Fenced code/diagram block: ```lang\n ... \n```  (lang optional). DOTALL so the
# body can span lines; non-greedy so adjacent blocks don't merge.
_FENCE_RE = re.compile(r"```[ \t]*([A-Za-z0-9_+-]*)[ \t]*\r?\n.*?```", re.DOTALL)

# Any markdown heading line (H1–H6), used to label a diagram with its section.
_ANY_HEADING_RE = re.compile(r"(?m)^#{1,6}\s+(.+?)\s*$")

# Fence languages we treat as renderable diagrams (the chat UI renders mermaid +
# ascii via MermaidBlock; plantuml/uml/graphviz are kept for forward-compat).
DIAGRAM_LANGS = {
    "mermaid", "ascii", "plantuml", "uml", "dot", "graphviz", "sequencediagram",
}


def iter_fenced_blocks(markdown: str) -> Iterator[tuple[int, int, str, str]]:
    """Yield (start, end, lang_lowercased, full_block_text) for every fenced
    block in `markdown`, in order. `full_block_text` includes the ``` fences."""
    if not markdown:
        return
    for m in _FENCE_RE.finditer(markdown):
        yield m.start(), m.end(), (m.group(1) or "").lower(), m.group(0)


def _nearest_heading(markdown: str, pos: int) -> str:
    """The text of the last heading that appears before `pos` (or '')."""
    best = ""
    for m in _ANY_HEADING_RE.finditer(markdown[:pos]):
        best = m.group(1).strip()
    return best


def extract_diagrams(markdown: str, kind: Optional[str] = None) -> List[dict]:
    """Pull every diagram fence out of the report markdown, intact.

    Returns a list of {"kind", "heading", "code"} where `code` is the verbatim
    ```fence``` block (ready to return to the chat, which renders it). `heading`
    is the nearest preceding section heading so the agent can label/cite it.
    `kind` filters to a single diagram language (e.g. "mermaid").
    """
    out: List[dict] = []
    if not markdown:
        return out
    want = kind.strip().lower() if kind else None
    for start, _end, lang, full in iter_fenced_blocks(markdown):
        if lang not in DIAGRAM_LANGS:
            continue
        if want and lang != want:
            continue
        out.append({
            "kind": lang or "mermaid",
            "heading": _nearest_heading(markdown, start),
            "code": full,
        })
    return out


# Friendly section name -> heading keywords, ordered MOST specific first. Matched
# case-insensitively as substrings of the parsed heading text. Lets the chat tool
# accept stable names (tech_stack, timeline, ...) regardless of the exact
# (numbered or un-numbered) heading the pipeline emitted. Order matters: the most
# specific alias that matches any heading wins (so "tech_stack" prefers
# "Recommended Tech Stack" over a generic "Architecture", and "timeline" prefers
# "Phased Roadmap" over "Cost & Effort Estimate").
_SECTION_ALIASES: dict[str, List[str]] = {
    "executive_summary": ["executive summary", "summary", "overview", "tl;dr"],
    "tech_stack": ["technology stack", "tech stack", "recommended tech", "technology", "stack", "solution architecture", "proposed architecture", "architecture"],
    "team_structure": ["team composition", "team structure", "staffing gaps", "staffing", "team", "resourcing", "roles", "squad"],
    "timeline": ["phased roadmap", "roadmap", "timeline", "schedule", "milestones", "delivery plan", "phases", "duration"],
    "risks": ["risks & mitigations", "risks and mitigations", "key risks", "risk register", "risk", "known issues", "gotchas", "concerns", "blind spots", "challenges"],
    "recommendations": ["recommendations", "recommendation", "next steps", "go/no-go", "verdict", "feasibility & cost", "feasibility"],
}


def find_section(sections: List[Section], name: str) -> Optional[Section]:
    """Resolve a friendly name / id / heading to a parsed Section, or None.

    Resolution order: exact section id -> exact heading -> alias-keyword match in
    priority order (most specific alias first, H2 before H3) -> heading substring.
    Empty input returns None.
    """
    if not sections or not name:
        return None
    raw = name.strip()
    key = raw.lower()

    for s in sections:  # exact id
        if s.id == raw:
            return s
    for s in sections:  # exact heading text
        if s.heading_text.lower() == key:
            return s

    # Priority match: try each alias in order; the first alias that hits any
    # heading wins (H2 preferred over H3 for that alias).
    aliases = _SECTION_ALIASES.get(key, [key])
    for alias in aliases:
        for level in (2, 3):
            for s in sections:
                if s.heading_level == level and alias in s.heading_text.lower():
                    return s

    for s in sections:  # last resort: the raw name appears in a heading
        if key in s.heading_text.lower():
            return s
    return None


def report_delivery_items(markdown: str, summary_report, scope: str = "risks",
                          section_ids: Optional[set] = None) -> tuple[str, List[dict]]:
    """Build (epic_description, items) for a report -> Jira/delivery export.

    scope 'risks'  -> one item per entry in the typed risk register.
    scope 'sections' -> one item per non-internal report section (optionally filtered
    to `section_ids`). Each item = {"summary", "description"}. Shared by the Jira
    REST endpoint and the push_to_jira chat tool so they stay in lockstep.
    """
    summary = summary_report if isinstance(summary_report, dict) else {}
    items: List[dict] = []

    if scope == "sections":
        ids = set(section_ids or [])
        for s in parse_sections(markdown or ""):
            if s.kind == "internal":
                continue
            if ids and s.id not in ids:
                continue
            items.append({"summary": s.heading_text, "description": s.raw_markdown})
        return ("Delivery work breakdown generated from the GroundedIQ analysis report.", items)

    risks = summary.get("key_risks") or summary.get("risks") or []
    if isinstance(risks, list):
        for r in risks:
            if isinstance(r, dict):
                title = r.get("risk") or r.get("title") or r.get("description") or "Risk"
                desc = r.get("mitigation") or r.get("impact") or ""
                items.append({"summary": str(title), "description": str(desc)})
            elif r:
                items.append({"summary": str(r), "description": ""})
    return ("Risk register exported from the GroundedIQ analysis report.", items)


def list_sections(markdown: str) -> List[dict]:
    """A lightweight table-of-contents for the report: id, heading, level, and
    whether the section contains a diagram. Powers the chat 'what's in here?'
    navigation and lets the agent cite sections."""
    sections = parse_sections(markdown)
    toc: List[dict] = []
    for s in sections:
        has_diagram = any(
            lang in DIAGRAM_LANGS for _s, _e, lang, _f in iter_fenced_blocks(s.raw_markdown)
        )
        toc.append({
            "id": s.id,
            "heading": s.heading_text,
            "level": s.heading_level,
            "kind": s.kind,
            "has_diagram": has_diagram,
        })
    return toc
