"""Eval gate for src/utils/deliverable_polish.polish_section.

This is the GATING test for the Deliverable Builder Polish feature. It runs the
real LLM against three fixture sections and asserts the contract that the
polish prompt promises:

1. Every named technology in tech_terms.txt that appeared in the source must
   still appear in the polished output. (We don't penalize the LLM for tech
   that wasn't in the source — only for *dropping* tech that was.)
2. Every numeric estimate in the source ($amounts, durations, percentages)
   must still appear in the polished output.
3. Every named risk in a Risks section (lines starting with `- **<name>**`)
   must survive.
4. The section heading line must be preserved exactly.
5. None of the banned hedge phrases or internal annotations may appear.

When OPENAI_CHATGPT is unset (e.g. CI without secrets), tests skip rather than
fail, so the import itself is safe. Run locally with:

    pytest tests/eval/deliverable_polish_eval.py -v

Iterate on the prompt in src/utils/deliverable_polish.py until green.
"""

from __future__ import annotations

import asyncio
import os
import re
import sys
from pathlib import Path

import pytest


FIXTURES_DIR = Path(__file__).parent / "fixtures"
TECH_TERMS_FILE = Path(__file__).parent / "tech_terms.txt"


def _load_tech_terms() -> list[str]:
    terms: list[str] = []
    for line in TECH_TERMS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        terms.append(line)
    return terms


def _strip_banned_lines(text: str) -> str:
    """Drop lines matching any banned-phrase regex.

    The polish prompt is contracted to remove these lines entirely (e.g.
    `impact_if_wrong: ...$120,000...`), so any numeric estimates that live
    *only* inside them are expected casualties — comparing them against the
    polished output would punish the LLM for following the prompt.
    """
    kept = []
    for line in text.splitlines():
        if any(re.search(pat, line, re.I) for pat in _BANNED):
            continue
        kept.append(line)
    return "\n".join(kept)


def _numeric_tokens(text: str) -> set[str]:
    """Extract dollar amounts, durations, percentages from non-banned lines only."""
    text = _strip_banned_lines(text)
    tokens: set[str] = set()
    # Dollar amounts: $1,200, $1.2M, $345,600, $50,000
    for m in re.finditer(r"\$[\d,]+(?:\.\d+)?[KMB]?", text):
        tokens.add(m.group(0))
    # Durations: 12 weeks, 26 weeks, 4 hrs, 18 months
    for m in re.finditer(r"\b\d+(?:\.\d+)?\s*(?:weeks?|days?|months?|years?|hrs?|hours?)\b", text, re.I):
        tokens.add(m.group(0).lower())
    # Percentages: 99.9%
    for m in re.finditer(r"\b\d+(?:\.\d+)?\s*%", text):
        tokens.add(m.group(0))
    return tokens


def _named_risks(text: str) -> set[str]:
    """Extract bolded names from Risks-style bullet lines: `- **Name**: ...`."""
    return {m.group(1).strip().lower() for m in re.finditer(r"^\s*-\s*\*\*([^*]+)\*\*", text, re.M)}


def _heading_line(text: str) -> str | None:
    for line in text.splitlines():
        if line.startswith("#"):
            return line.strip()
    return None


# Phrases the polish prompt promises to remove. Match case-insensitively but
# require word boundaries so we don't false-positive on substrings like "may"
# inside "Maycomb". We keep this list aligned with the REMOVE block of the
# polish prompt; if the prompt grows, this list grows.
_BANNED = [
    r"\bwe believe\b",
    r"\bTBD\b",
    r"\bto be confirmed\b",
    r"\bto be determined\b",
    r"\brisk_level\s*:",
    r"\bimpact_if_wrong\s*:",
    r"\bconfidence\s*:\s*low\b",
    r"\[needs validation[^\]]*\]",
    r"\[draft\]",
]


@pytest.fixture(scope="module")
def polish_fn():
    # Load the project .env so OPENAI_CHATGPT is populated when running locally.
    repo_root = Path(__file__).resolve().parents[2]
    try:
        from dotenv import load_dotenv
        load_dotenv(repo_root / ".env")
    except ImportError:
        pass

    if not os.getenv("OPENAI_CHATGPT"):
        pytest.skip("OPENAI_CHATGPT not set; skipping live polish eval")

    # The polish module's transitive imports (agents.agentic_workflow,
    # utils.llm_metrics, utils.logger) are package-relative under src/, so
    # src/ has to be on sys.path before we import.
    src_path = str(repo_root / "src")
    if src_path not in sys.path:
        sys.path.insert(0, src_path)

    from utils.deliverable_polish import polish_section
    return polish_section


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if not asyncio.iscoroutine(coro) else asyncio.run(coro)


@pytest.mark.parametrize("fixture_name", [
    "section_recommended_architecture.md",
    "section_effort_estimate.md",
    "section_risks.md",
])
def test_polish_preserves_contract(polish_fn, fixture_name):
    source = (FIXTURES_DIR / fixture_name).read_text(encoding="utf-8")
    polished = asyncio.run(polish_fn(source))

    assert polished and polished.strip(), "polish_section returned empty output"

    # 1. Heading preserved.
    src_heading = _heading_line(source)
    out_heading = _heading_line(polished)
    assert src_heading is not None, "fixture has no heading — fix the fixture"
    assert out_heading == src_heading, (
        f"Heading changed.\n  source: {src_heading!r}\n  polished: {out_heading!r}"
    )

    # 2. Tech terms that appeared in source must survive.
    src_lower = source.lower()
    out_lower = polished.lower()
    missing_tech = [
        term for term in _load_tech_terms()
        if term.lower() in src_lower and term.lower() not in out_lower
    ]
    assert not missing_tech, f"Polish dropped named technologies: {missing_tech}"

    # 3. Numeric tokens preserved.
    src_nums = _numeric_tokens(source)
    out_nums = _numeric_tokens(polished)
    # Compare lowercased duration tokens via the function's own normalization;
    # dollar/percent kept as-is.
    missing_nums = src_nums - out_nums
    assert not missing_nums, f"Polish dropped numeric estimates: {sorted(missing_nums)}"

    # 4. Named risks survive (only meaningful for the risks fixture, but cheap to run on all).
    missing_risks = _named_risks(source) - _named_risks(polished)
    assert not missing_risks, f"Polish dropped named risks: {sorted(missing_risks)}"

    # 5. No banned hedge phrases or internal annotations survive.
    survivors = [pat for pat in _BANNED if re.search(pat, polished, re.I)]
    assert not survivors, f"Polish failed to remove banned phrases: {survivors}"
