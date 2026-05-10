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


# Matches `## 3. Title` or `### 3.2 Title` (and 4 dot variants like `### 3.2.1`).
# Group 1 = hash prefix (## or ###), Group 2 = dotted number, Group 3 = title.
_HEADING_RE = re.compile(r"^(#{2,3})\s+([\d.]+?)\.?\s+(.+?)\s*$")

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
        number = m.group(2)
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

    for i, (line_idx, level, number, title) in enumerate(headings):
        # Each section's content ends at the NEXT heading of any level we
        # parse (H2 or H3). For an H2 with H3 children, this means the H2's
        # raw_markdown is just its heading + any prelude text before the
        # first H3 — the H3 children own their own bodies. Without this, the
        # H2 would duplicate every H3 inside it.
        end_idx = headings[i + 1][0] if i + 1 < len(headings) else len(lines)

        raw = "\n".join(lines[line_idx:end_idx]).rstrip() + "\n"
        section_id = _make_id(number, title)
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
