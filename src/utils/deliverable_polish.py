"""
Per-section LLM polish for the Deliverable Builder (A5).

The polish pass is intentionally **scoped to one section at a time** and
**triggered by the user**, not by a default toggle. The LLM assists; the
user decides. Whole-report auto-rewrite was rejected during planning
because it concentrates incident risk and bypasses the BA's editorial
authority over a client-facing artifact.

Behavior contract for the prompt:
- INPUT: a single section's markdown including its heading.
- OUTPUT: the same section, same heading, in client-ready tone.
- PRESERVE (hard rule, gated by tests/eval/deliverable_polish_eval.py):
    * every named technology
    * every numeric estimate ($amounts, durations in weeks/days/months/hrs)
    * the section's heading text and level
- REMOVE:
    * hedge phrases ("we believe", "TBD", "this may", "to be confirmed")
    * `risk_level: high|med|low` and `impact_if_wrong:` style annotations
    * meta-commentary about the analysis pipeline
- DO NOT invent new content. Do not add disclaimers. Do not summarize away detail.
"""

from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from agents.agentic_workflow import llm, invoke_with_timeout
from utils.llm_metrics import hash_prompt
from utils.logger import logger


_POLISH_PROMPT = """\
You are polishing a single section of a consulting deliverable so it can be sent to a client buyer.

INPUT SECTION (markdown):
---
{section_markdown}
---

REWRITE THIS SECTION FOR A CLIENT AUDIENCE.

PRESERVE (do not drop or reword):
- Every named technology, framework, vendor, product, or service.
- Every numeric estimate: dollar amounts (e.g. "$1.2M", "$50,000"), durations (weeks, days, months, hours), percentages, counts of engineers / regions / replicas.
- The section's exact heading line (same level, same text, same number prefix).
- Every named risk in a risks register.

REMOVE:
- Hedge language: "we believe", "may", "might", "could potentially", "TBD", "to be confirmed", "to be determined".
- Internal triage annotations: anything that looks like `risk_level: high`, `impact_if_wrong: ...`, `confidence: low`.
- Meta-commentary about the analysis pipeline, agents, or how the report was generated.
- Bracketed editorial notes like `[needs validation]`, `[draft]`.

REWRITE STYLE:
- Declarative and confident, not hedging.
- Keep all bullet points and tables; do not collapse lists into prose.
- Do not add new disclaimers, caveats, or sections.
- Do not invent technologies, numbers, or risks that are not in the input.

OUTPUT: only the rewritten markdown section, beginning with its heading line. No preamble, no explanation, no fenced code block wrapping.
"""

_PROMPT_HASH = hash_prompt(_POLISH_PROMPT)


def _strip_fence_wrapper(text: str) -> str:
    """Some models insist on wrapping output in ```markdown ... ```. Strip it."""
    s = text.strip()
    if s.startswith("```"):
        # drop the opening fence (with optional language) up to the next newline
        first_nl = s.find("\n")
        if first_nl != -1:
            s = s[first_nl + 1 :]
        if s.endswith("```"):
            s = s[: -3].rstrip()
    return s


async def polish_section(section_markdown: str) -> str:
    """Run the polish pass against a single section. Returns rewritten markdown.

    Reuses the shared `llm` instance (GENERATING_REPORT_MODEL) and the
    standard timeout/retry plumbing from agentic_workflow.invoke_with_timeout
    so this inherits the same observability as the pipeline agents.
    """
    if not section_markdown or not section_markdown.strip():
        return section_markdown

    chain = ChatPromptTemplate.from_template(_POLISH_PROMPT) | llm | StrOutputParser()
    response = await invoke_with_timeout(
        chain,
        {"section_markdown": section_markdown},
        agent_name="deliverable_polish_section",
        prompt_hash=_PROMPT_HASH,
    )
    polished = _strip_fence_wrapper(response or "")
    if not polished.strip():
        logger.warning("polish_section returned empty output; falling back to source markdown")
        return section_markdown
    return polished
