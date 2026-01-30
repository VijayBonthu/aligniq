"""
Answer Analyzer Agent

Analyzes user-provided answers against the original document and questions to:
1. Detect contradictions between answers
2. Identify vague or unclear answers
3. Determine which questions are no longer relevant
4. Calculate readiness score for full report generation
5. Generate list of assumptions for unanswered questions

Usage:
    result = await analyze_answers(
        presales_id="...",
        document="...",
        scanned_requirements={...},
        questions_with_answers=[...]
    )
"""

import json
import time
import asyncio
from typing import Dict, List, Any, Optional
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langchain.output_parsers import OutputFixingParser
from config import settings
from utils.presales_prompts import ANSWER_ANALYZER_PROMPT, READINESS_SUMMARY_PROMPT
from utils.logger import logger


# =============================================================================
# LLM CONFIGURATION
# =============================================================================

# Use stronger model for analysis (needs good reasoning)
llm_analyzer = ChatOpenAI(
    api_key=settings.OPENAI_CHATGPT,
    model=settings.GENERATING_REPORT_MODEL,
    temperature=0.1,
    request_timeout=120
)

# Parser for JSON responses
llm_parser = ChatOpenAI(
    api_key=settings.OPENAI_CHATGPT,
    model=settings.SUMMARIZATION_MODEL,
    temperature=0
)
json_parser = JsonOutputParser()
fixed_parser = OutputFixingParser.from_llm(parser=json_parser, llm=llm_parser)


# =============================================================================
# DATA STRUCTURES
# =============================================================================

class AnalysisResult:
    """Result of answer analysis"""

    def __init__(self, raw_result: Dict[str, Any]):
        self.contradictions = raw_result.get("contradictions", [])
        self.vague_answers = raw_result.get("vague_answers", [])
        self.invalidated_questions = raw_result.get("invalidated_questions", [])
        self.readiness = raw_result.get("readiness", {})
        self.assumptions = raw_result.get("assumptions", [])
        self.follow_up_questions = raw_result.get("follow_up_questions", [])
        self.recommendations = raw_result.get("recommendations", [])
        self.processing_time_ms = raw_result.get("processing_time_ms", 0)

    @property
    def readiness_score(self) -> float:
        return self.readiness.get("score", 0.0)

    @property
    def readiness_status(self) -> str:
        return self.readiness.get("status", "not_analyzed")

    @property
    def has_issues(self) -> bool:
        return len(self.contradictions) > 0 or len(self.vague_answers) > 0

    @property
    def can_generate_report(self) -> bool:
        """Check if we can proceed with report generation (possibly with assumptions)"""
        # Can generate if ready OR ready_with_assumptions OR even needs_more_info (with consent)
        # We let the user decide - they can always generate with assumptions
        return self.readiness_status in ["ready", "ready_with_assumptions", "needs_more_info"]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "contradictions": self.contradictions,
            "vague_answers": self.vague_answers,
            "invalidated_questions": self.invalidated_questions,
            "readiness": self.readiness,
            "assumptions": self.assumptions,
            "follow_up_questions": self.follow_up_questions,
            "recommendations": self.recommendations,
            "processing_time_ms": self.processing_time_ms
        }


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def format_questions_for_analysis(questions: List[Dict]) -> str:
    """
    Format questions and answers for the analyzer prompt.

    Args:
        questions: List of question dicts with answers

    Returns:
        Formatted string for the prompt
    """
    formatted = []

    for q in questions:
        q_type = q.get("question_type", "unknown")
        q_num = q.get("question_number", "?")
        q_text = q.get("question_text", "")
        answer = q.get("answer", "")
        status = q.get("status", "pending")

        if q_type == "p1_blocker":
            title = q.get("title", "")
            why = q.get("description", "")
            formatted.append(f"""
### {q_num} (P1 Blocker) - {status.upper()}
**Issue:** {title}
**Why it matters:** {why}
**Question:** {q_text}
**Answer:** {answer if answer else "[NOT ANSWERED]"}
""")
        else:
            category = q.get("area_or_category", "")
            why = q.get("description", "")
            formatted.append(f"""
### {q_num} (Kickstart - {category}) - {status.upper()}
**Question:** {q_text}
**Why critical:** {why}
**Answer:** {answer if answer else "[NOT ANSWERED]"}
""")

    return "\n".join(formatted)


def parse_json_response(content: str) -> dict:
    """Parse JSON from LLM response, handling markdown code blocks."""
    try:
        # Handle markdown code blocks
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        return json.loads(content.strip())
    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error in answer analyzer: {str(e)}")
        logger.debug(f"Raw content: {content[:500]}...")
        raise ValueError(f"Failed to parse analyzer response as JSON: {str(e)}")


# =============================================================================
# MAIN ANALYSIS FUNCTION
# =============================================================================

async def analyze_answers(
    document: str,
    scanned_requirements: Dict[str, Any],
    questions: List[Dict[str, Any]],
    timeout: int = 120
) -> AnalysisResult:
    """
    Analyze user-provided answers for quality, contradictions, and readiness.

    Args:
        document: Original document text
        scanned_requirements: Requirements extracted by scanner agent
        questions: List of questions with their answers
        timeout: Timeout in seconds

    Returns:
        AnalysisResult with contradictions, vague answers, readiness, assumptions

    Raises:
        ValueError: If analysis fails
        asyncio.TimeoutError: If analysis times out
    """
    logger.info("Starting answer analysis")
    start_time = time.time()

    # Format questions for the prompt
    questions_formatted = format_questions_for_analysis(questions)

    # Count answered vs total
    total_questions = len(questions)
    answered_questions = sum(1 for q in questions if q.get("answer"))
    logger.info(f"Analyzing {answered_questions}/{total_questions} answered questions")

    try:
        prompt = ChatPromptTemplate.from_template(ANSWER_ANALYZER_PROMPT)
        chain = prompt | llm_analyzer | fixed_parser

        response = await asyncio.wait_for(
            chain.ainvoke({
                "document": document[:15000],  # Limit document size
                "scanned_requirements": json.dumps(scanned_requirements, indent=2)[:5000],
                "questions_with_answers": questions_formatted
            }),
            timeout=timeout
        )

        # Response should be parsed by fixed_parser
        if isinstance(response, str):
            response = parse_json_response(response)

        # Add processing time
        processing_time_ms = int((time.time() - start_time) * 1000)
        response["processing_time_ms"] = processing_time_ms

        logger.info(f"Answer analysis completed in {processing_time_ms}ms")
        logger.info(f"Readiness score: {response.get('readiness', {}).get('score', 0)}")
        logger.info(f"Contradictions found: {len(response.get('contradictions', []))}")
        logger.info(f"Vague answers found: {len(response.get('vague_answers', []))}")

        return AnalysisResult(response)

    except asyncio.TimeoutError:
        logger.error(f"Answer analysis timed out after {timeout}s")
        raise
    except Exception as e:
        logger.error(f"Answer analysis failed: {str(e)}")
        raise ValueError(f"Answer analysis failed: {str(e)}")


async def analyze_answers_quick(
    questions: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Quick local analysis without LLM call.

    Used for immediate feedback before full analysis.
    Returns basic stats only.

    Args:
        questions: List of questions with their answers

    Returns:
        Dict with basic readiness stats
    """
    p1_questions = [q for q in questions if q.get("question_type") == "p1_blocker"]
    kickstart_questions = [q for q in questions if q.get("question_type") == "kickstart"]

    p1_answered = sum(1 for q in p1_questions if q.get("answer"))
    kickstart_answered = sum(1 for q in kickstart_questions if q.get("answer"))

    p1_total = len(p1_questions)
    kickstart_total = len(kickstart_questions)

    # Simple scoring: P1s are weighted 2x
    if p1_total + kickstart_total == 0:
        score = 0.0
    else:
        p1_weight = 2.0
        kickstart_weight = 1.0
        max_score = (p1_total * p1_weight) + (kickstart_total * kickstart_weight)
        actual_score = (p1_answered * p1_weight) + (kickstart_answered * kickstart_weight)
        score = actual_score / max_score if max_score > 0 else 0.0

    # Determine status
    if score >= 0.9:
        status = "ready"
    elif score >= 0.5:
        status = "ready_with_assumptions"
    else:
        status = "needs_more_info"

    return {
        "readiness": {
            "score": round(score, 2),
            "status": status,
            "p1_answered": p1_answered,
            "p1_total": p1_total,
            "kickstart_answered": kickstart_answered,
            "kickstart_total": kickstart_total,
            "summary": f"{p1_answered}/{p1_total} P1 blockers and {kickstart_answered}/{kickstart_total} kickstart questions answered"
        }
    }


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    'analyze_answers',
    'analyze_answers_quick',
    'AnalysisResult',
    'format_questions_for_analysis'
]
