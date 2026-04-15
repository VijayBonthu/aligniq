"""
LangChain Tool Definitions for /chat-with-doc endpoint.
Uses @tool decorator for automatic schema generation.

These tools enable the LLM to directly interact with pending changes,
document search, and report operations.
"""

from langchain_core.tools import tool
from typing import List, Optional, Any
import json
from utils.logger import logger


# ============= CONTEXT HOLDER =============
# Set these before invoking the agent
class ToolContext:
    """Holds context (chat_history_id, db, user_id) for tool execution."""
    chat_history_id: str = None
    db: Any = None
    user_id: str = None  # REQUIRED for get_regeneration_context and create_new_report_version

tool_context = ToolContext()


# ============= READ-ONLY TOOLS =============

@tool
async def get_pending_changes() -> str:
    """
    Get all pending changes for the current document.
    Returns a list of changes with their IDs (CHG-001, CHG-002, etc.), descriptions, and status.
    Use this to show users their queued modifications before regenerating the report.
    """
    from database_scripts import get_pending_changes as db_get_pending

    try:
        changes = await db_get_pending(tool_context.chat_history_id, tool_context.db)

        if not changes:
            return json.dumps({
                "status": "empty",
                "message": "No pending changes. You can suggest modifications to the report.",
                "changes": [],
                "count": 0
            })

        return json.dumps({
            "status": "success",
            "count": len(changes),
            "changes": changes
        })
    except Exception as e:
        logger.error(f"Error in get_pending_changes tool: {str(e)}")
        return json.dumps({"status": "error", "message": str(e)})


@tool
async def search_document(query: str, max_results: int = 5) -> str:
    """
    Search the uploaded document and report for specific content using semantic search.
    Use this to find relevant sections when user asks questions about the document or report content.

    Args:
        query: The search query to find relevant document sections
        max_results: Maximum number of results to return (default: 5)
    """
    from vectordb.vector_db import retrieve_similar_embeddings
    from config import settings

    try:
        results = await retrieve_similar_embeddings(
            query_text=query,
            chat_history_id=tool_context.chat_history_id,
            model=settings.EMBEDDING_MODEL,
            top_k=max_results
        )

        # Extract documents from nested Chroma structure
        # Chroma returns: {"documents": [["doc1", "doc2"]], "metadatas": [[{...}]], "distances": [[...]]}
        extracted_docs = []
        if results and "documents" in results and results["documents"]:
            extracted_docs = results["documents"][0]  # Unwrap the nested array

        # Extract metadata if available
        extracted_metadata = []
        if results and "metadatas" in results and results["metadatas"]:
            extracted_metadata = results["metadatas"][0]

        # Extract distances/relevance scores if available
        distances = []
        if results and "distances" in results and results["distances"]:
            distances = results["distances"][0]

        # Format results for LLM consumption
        formatted_results = []
        for i, doc in enumerate(extracted_docs):
            result_item = {
                "content": doc,
                "relevance_rank": i + 1
            }
            if i < len(extracted_metadata):
                result_item["metadata"] = extracted_metadata[i]
            if i < len(distances):
                result_item["similarity_score"] = 1 - distances[i]  # Convert distance to similarity
            formatted_results.append(result_item)

        # Create combined context for easy LLM use
        combined_context = "\n\n---\n\n".join(extracted_docs) if extracted_docs else ""

        return json.dumps({
            "status": "success",
            "query": query,
            "results_count": len(formatted_results),
            "results": formatted_results,
            "combined_context": combined_context
        })
    except Exception as e:
        logger.error(f"Error in search_document tool: {str(e)}")
        return json.dumps({"status": "error", "message": str(e)})


@tool
async def get_report_section(section_name: str) -> str:
    """
    Get a specific section from the generated report.

    Args:
        section_name: One of: executive_summary, tech_stack, team_structure,
                      timeline, risks, recommendations, or full_report for everything
    """
    from database_scripts import get_summary_report

    try:
        report = await get_summary_report(tool_context.chat_history_id, tool_context.db)

        if not report or not report.report_content:
            return json.dumps({"status": "error", "message": "No report found. The analysis may not be complete yet."})

        content = report.report_content

        if section_name == "full_report":
            return json.dumps({
                "status": "success",
                "section": "full_report",
                "content": content
            })
        elif isinstance(content, dict) and section_name in content:
            return json.dumps({
                "status": "success",
                "section": section_name,
                "content": content[section_name]
            })
        else:
            available = list(content.keys()) if isinstance(content, dict) else []
            return json.dumps({
                "status": "error",
                "message": f"Section '{section_name}' not found",
                "available_sections": available
            })
    except Exception as e:
        logger.error(f"Error in get_report_section tool: {str(e)}")
        return json.dumps({"status": "error", "message": str(e)})


@tool
async def search_report_section(query: str, section: str = None) -> str:
    """
    Search for specific information within a report section.
    Combines direct section retrieval with semantic search for comprehensive answers.
    Use this when user asks detailed questions about specific aspects of the report.

    Args:
        query: What to search for (e.g., "database choice rationale", "team size")
        section: Optional section filter (timeline, risks, estimates, architecture, team_structure, tech_stack)
    """
    from database_scripts import get_summary_report
    from vectordb.vector_db import retrieve_similar_embeddings
    from config import settings

    try:
        results = {
            "status": "success",
            "query": query,
            "section_filter": section
        }

        # Get report section directly if specified
        if section:
            report = await get_summary_report(tool_context.chat_history_id, tool_context.db)
            if report and report.summary_report:
                summary = report.summary_report
                if isinstance(summary, dict) and section in summary:
                    results["section_content"] = summary[section]
                elif isinstance(summary, dict):
                    # Try to find matching section
                    for key in summary.keys():
                        if section.lower() in key.lower():
                            results["section_content"] = summary[key]
                            results["matched_section"] = key
                            break

        # Also do semantic search for additional context
        vector_results = await retrieve_similar_embeddings(
            query_text=query,
            chat_history_id=tool_context.chat_history_id,
            model=settings.EMBEDDING_MODEL,
            top_k=3
        )

        # Extract documents from nested Chroma structure
        if vector_results and "documents" in vector_results and vector_results["documents"]:
            extracted_docs = vector_results["documents"][0]
            results["related_content"] = extracted_docs
            results["combined_context"] = "\n\n---\n\n".join(extracted_docs)

        return json.dumps(results)
    except Exception as e:
        logger.error(f"Error in search_report_section tool: {str(e)}")
        return json.dumps({"status": "error", "message": str(e)})


@tool
async def get_risks_and_mitigations() -> str:
    """
    Get all identified risks and their mitigation strategies from the report.
    Use this when user asks about risks, concerns, challenges, or what could go wrong.
    Returns structured risk information including severity, impact, and recommended mitigations.
    """
    from database_scripts import get_summary_report
    from vectordb.vector_db import retrieve_similar_embeddings
    from config import settings

    try:
        report = await get_summary_report(tool_context.chat_history_id, tool_context.db)

        results = {
            "status": "success"
        }

        # Get risks section from summary report
        if report and report.summary_report:
            summary = report.summary_report
            if isinstance(summary, dict):
                # Look for risks section
                for key in summary.keys():
                    if "risk" in key.lower() or "concern" in key.lower() or "challenge" in key.lower():
                        results["risks_section"] = summary[key]
                        results["section_name"] = key
                        break

        # Also search vector DB for risk-related content
        vector_results = await retrieve_similar_embeddings(
            query_text="risks concerns challenges mitigations what could go wrong",
            chat_history_id=tool_context.chat_history_id,
            model=settings.EMBEDDING_MODEL,
            top_k=5
        )

        if vector_results and "documents" in vector_results and vector_results["documents"]:
            extracted_docs = vector_results["documents"][0]
            results["risk_related_content"] = extracted_docs

        if not results.get("risks_section") and not results.get("risk_related_content"):
            results["status"] = "not_found"
            results["message"] = "No specific risk information found in the report. The analysis may not have identified explicit risks."

        return json.dumps(results)
    except Exception as e:
        logger.error(f"Error in get_risks_and_mitigations tool: {str(e)}")
        return json.dumps({"status": "error", "message": str(e)})


@tool
async def suggest_optimization(constraint_type: str, constraint_details: str) -> str:
    """
    Generate optimization suggestion based on user's constraint.
    Call this when user mentions budget, timeline, or resource constraints.
    Returns optimization suggestions with trade-offs clearly explained.

    Args:
        constraint_type: Type of constraint - "budget", "timeline", "resource", or "scope"
        constraint_details: What the user said about the constraint (e.g., "budget is limited to $50k")
    """
    from database_scripts import get_summary_report
    from langchain_openai import ChatOpenAI
    from config import settings

    try:
        # Get relevant report sections
        report = await get_summary_report(tool_context.chat_history_id, tool_context.db)

        if not report or not report.summary_report:
            return json.dumps({
                "status": "error",
                "message": "No report found to analyze for optimizations."
            })

        summary = report.summary_report
        report_content = report.report_content if report.report_content else ""

        # Build context based on constraint type
        relevant_sections = []
        if isinstance(summary, dict):
            for key, value in summary.items():
                if constraint_type == "budget" and any(k in key.lower() for k in ["cost", "estimate", "budget", "pricing"]):
                    relevant_sections.append(f"**{key}**:\n{value}")
                elif constraint_type == "timeline" and any(k in key.lower() for k in ["timeline", "schedule", "phase", "milestone"]):
                    relevant_sections.append(f"**{key}**:\n{value}")
                elif constraint_type == "resource" and any(k in key.lower() for k in ["team", "resource", "staff", "role"]):
                    relevant_sections.append(f"**{key}**:\n{value}")
                elif constraint_type == "scope" and any(k in key.lower() for k in ["requirement", "feature", "scope", "mvp"]):
                    relevant_sections.append(f"**{key}**:\n{value}")

        context = "\n\n".join(relevant_sections) if relevant_sections else str(summary)[:3000]

        # Generate optimization suggestion using LLM
        llm = ChatOpenAI(
            model=settings.GENERATING_REPORT_MODEL,
            api_key=settings.OPENAI_CHATGPT,
            temperature=0.3
        )

        optimization_prompt = f"""Based on the following project report context and the user's constraint, suggest ONE specific optimization.

CONSTRAINT TYPE: {constraint_type}
USER'S CONSTRAINT: {constraint_details}

RELEVANT REPORT SECTIONS:
{context}

Generate a specific, actionable optimization suggestion that addresses this constraint.
Format your response as JSON with these fields:
- optimization: Brief description of the optimization (1-2 sentences)
- impact: How this helps address the constraint
- trade_off: What you give up or risk with this optimization
- affected_sections: List of report sections that would need updating
- implementation_notes: Brief notes on how to implement this change

Be specific and reference actual recommendations from the report."""

        response = await llm.ainvoke(optimization_prompt)

        try:
            # Try to parse as JSON
            import re
            json_match = re.search(r'\{[\s\S]*\}', response.content)
            if json_match:
                optimization = json.loads(json_match.group())
            else:
                optimization = {"optimization": response.content, "raw_response": True}
        except json.JSONDecodeError:
            optimization = {"optimization": response.content, "raw_response": True}

        return json.dumps({
            "status": "success",
            "constraint_type": constraint_type,
            "constraint_details": constraint_details,
            "suggestion": optimization,
            "can_track_as_change": True,
            "prompt": "Would you like me to track this as a pending change for deeper analysis?"
        })
    except Exception as e:
        logger.error(f"Error in suggest_optimization tool: {str(e)}")
        return json.dumps({"status": "error", "message": str(e)})


@tool
async def analyze_cost_reduction() -> str:
    """
    Analyze the report and suggest cost reduction opportunities.
    Returns a prioritized list of cost-saving suggestions with trade-offs.
    Use this when user mentions budget concerns or asks about reducing costs.
    """
    from database_scripts import get_summary_report
    from langchain_openai import ChatOpenAI
    from config import settings

    try:
        report = await get_summary_report(tool_context.chat_history_id, tool_context.db)

        if not report or not report.summary_report:
            return json.dumps({
                "status": "error",
                "message": "No report found to analyze for cost reductions."
            })

        summary = report.summary_report
        report_content = report.report_content if report.report_content else str(summary)

        # Use LLM to analyze for cost reduction opportunities
        llm = ChatOpenAI(
            model=settings.GENERATING_REPORT_MODEL,
            api_key=settings.OPENAI_CHATGPT,
            temperature=0.3
        )

        analysis_prompt = f"""Analyze this project report and identify cost reduction opportunities.

REPORT CONTENT:
{str(report_content)[:6000]}

Identify 3-5 specific cost reduction opportunities. For each, provide:
1. The current recommendation and estimated cost impact
2. A cost-effective alternative
3. The trade-off involved
4. Estimated savings (if quantifiable)

Format as a numbered list with clear sections for each opportunity.
Focus on actionable changes that could be tracked as pending changes."""

        response = await llm.ainvoke(analysis_prompt)

        return json.dumps({
            "status": "success",
            "analysis_type": "cost_reduction",
            "opportunities": response.content,
            "can_track_as_changes": True,
            "prompt": "Would you like me to track any of these as pending changes?"
        })
    except Exception as e:
        logger.error(f"Error in analyze_cost_reduction tool: {str(e)}")
        return json.dumps({"status": "error", "message": str(e)})


@tool
async def analyze_timeline_acceleration() -> str:
    """
    Analyze the report and suggest ways to accelerate the timeline.
    Returns a prioritized list of timeline optimization suggestions with trade-offs.
    Use this when user mentions tight deadlines or asks about speeding up delivery.
    """
    from database_scripts import get_summary_report
    from langchain_openai import ChatOpenAI
    from config import settings

    try:
        report = await get_summary_report(tool_context.chat_history_id, tool_context.db)

        if not report or not report.summary_report:
            return json.dumps({
                "status": "error",
                "message": "No report found to analyze for timeline acceleration."
            })

        summary = report.summary_report
        report_content = report.report_content if report.report_content else str(summary)

        # Use LLM to analyze for timeline acceleration
        llm = ChatOpenAI(
            model=settings.GENERATING_REPORT_MODEL,
            api_key=settings.OPENAI_CHATGPT,
            temperature=0.3
        )

        analysis_prompt = f"""Analyze this project report and identify timeline acceleration opportunities.

REPORT CONTENT:
{str(report_content)[:6000]}

Identify 3-5 specific ways to accelerate the project timeline. For each, provide:
1. The current timeline element or phase
2. How it could be accelerated
3. The trade-offs (quality, cost, scope implications)
4. Estimated time savings

Consider:
- Parallel work opportunities
- MVP/phased delivery approaches
- Technology choices that reduce development time
- Resource allocation changes

Format as a numbered list with clear sections for each opportunity.
Focus on actionable changes that could be tracked as pending changes."""

        response = await llm.ainvoke(analysis_prompt)

        return json.dumps({
            "status": "success",
            "analysis_type": "timeline_acceleration",
            "opportunities": response.content,
            "can_track_as_changes": True,
            "prompt": "Would you like me to track any of these as pending changes?"
        })
    except Exception as e:
        logger.error(f"Error in analyze_timeline_acceleration tool: {str(e)}")
        return json.dumps({"status": "error", "message": str(e)})


# ============= PERSONA-SPECIFIC BRIEFING TOOLS =============

@tool
async def prepare_client_meeting_brief(focus_areas: str = None) -> str:
    """
    Prepare a comprehensive briefing for a PM's client meeting.
    Extracts and synthesizes: blockers to discuss, questions needing client answers,
    risks to communicate, and responses for potential pushback.

    Args:
        focus_areas: Optional specific areas to focus on (timeline, budget, technical, scope)
    """
    from database_scripts import get_summary_report
    from langchain_openai import ChatOpenAI
    from config import settings

    try:
        report = await get_summary_report(tool_context.chat_history_id, tool_context.db)

        if not report or not report.summary_report:
            return json.dumps({
                "status": "error",
                "message": "No report found. Generate a report first before preparing meeting brief."
            })

        summary = report.summary_report
        report_content = report.report_content if report.report_content else ""

        # Extract key data from summary_report
        critical_assumptions = summary.get("critical_assumptions", []) if isinstance(summary, dict) else []
        key_risks = summary.get("key_risks", []) if isinstance(summary, dict) else []
        open_questions = summary.get("open_questions_for_client", []) if isinstance(summary, dict) else []
        alternatives = summary.get("alternative_architectures", []) if isinstance(summary, dict) else []

        # Try to get presales data if available
        presales_data = None
        try:
            from database_scripts import get_presales_by_chat_history
            presales = await get_presales_by_chat_history(tool_context.chat_history_id, tool_context.db)
            if presales:
                presales_data = {
                    "blind_spots": getattr(presales, 'blind_spots', None),
                    "p1_blockers": getattr(presales, 'p1_blockers', None),
                    "red_flags": getattr(presales, 'red_flags', None),
                    "critical_unknowns": getattr(presales, 'critical_unknowns', None)
                }
        except Exception:
            pass  # Presales data not available

        # Use LLM to synthesize into meeting brief
        llm = ChatOpenAI(
            model=settings.GENERATING_REPORT_MODEL,
            api_key=settings.OPENAI_CHATGPT,
            temperature=0.3
        )

        brief_prompt = f"""You are preparing a client meeting brief for a Project Manager.

REPORT DATA:
- Critical Assumptions: {json.dumps(critical_assumptions)}
- Key Risks: {json.dumps(key_risks)}
- Open Questions for Client: {json.dumps(open_questions)}
- Alternative Architectures Considered: {json.dumps(alternatives)}
{f'- Presales Analysis: {json.dumps(presales_data)}' if presales_data else ''}

{f'FOCUS AREAS: {focus_areas}' if focus_areas else ''}

Create a meeting brief with these sections:

1. **MUST DISCUSS (Blockers)** - What can't we proceed without? List assumptions that need validation.

2. **QUESTIONS FOR CLIENT** - Specific questions with why each matters (impact on timeline/budget/scope)

3. **RISKS TO COMMUNICATE** - Top 3-5 risks with severity and what client should know

4. **IF CLIENT PUSHES BACK** - Prepared responses for common objections (timeline, cost, complexity)

5. **DECISION POINTS** - What specific decisions do we need from the client in this meeting?

Be specific and actionable. Use the actual data from the report."""

        response = await llm.ainvoke(brief_prompt)

        return json.dumps({
            "status": "success",
            "brief_type": "client_meeting",
            "focus_areas": focus_areas,
            "brief": response.content,
            "source_data": {
                "assumptions_count": len(critical_assumptions),
                "risks_count": len(key_risks),
                "open_questions_count": len(open_questions),
                "has_presales_data": presales_data is not None
            }
        })
    except Exception as e:
        logger.error(f"Error in prepare_client_meeting_brief tool: {str(e)}")
        return json.dumps({"status": "error", "message": str(e)})


@tool
async def prepare_executive_summary(include_recommendation: bool = True) -> str:
    """
    Prepare an executive-level summary for go/no-go decisions.
    Includes: budget range with confidence, timeline with confidence, risk assessment,
    blockers count, and clear recommendation with caveats.

    Args:
        include_recommendation: Whether to include a go/no-go recommendation (default: True)
    """
    from database_scripts import get_summary_report
    from langchain_openai import ChatOpenAI
    from config import settings

    try:
        report = await get_summary_report(tool_context.chat_history_id, tool_context.db)

        if not report or not report.summary_report:
            return json.dumps({
                "status": "error",
                "message": "No report found for executive summary."
            })

        summary = report.summary_report
        report_content = report.report_content if report.report_content else ""

        # Extract structured data
        critical_assumptions = summary.get("critical_assumptions", []) if isinstance(summary, dict) else []
        key_risks = summary.get("key_risks", []) if isinstance(summary, dict) else []
        open_questions = summary.get("open_questions_for_client", []) if isinstance(summary, dict) else []

        # Use LLM to create executive summary
        llm = ChatOpenAI(
            model=settings.GENERATING_REPORT_MODEL,
            api_key=settings.OPENAI_CHATGPT,
            temperature=0.3
        )

        exec_prompt = f"""Create an executive decision brief based on this project analysis.

REPORT CONTENT (for estimates and details):
{str(report_content)[:8000]}

STRUCTURED DATA:
- Critical Assumptions: {json.dumps(critical_assumptions)}
- Key Risks: {json.dumps(key_risks)}
- Open Questions: {json.dumps(open_questions)}

Create an executive brief with:

1. **{'RECOMMENDATION' if include_recommendation else 'ASSESSMENT'}**: {'GO / CONDITIONAL GO / NO-GO with clear reasoning' if include_recommendation else 'Current readiness assessment'}

2. **BUDGET**: $X - $Y range with confidence percentage and what affects it

3. **TIMELINE**: X-Y weeks (MVP) and X-Y weeks (Production) with confidence percentage

4. **TOP 3 RISKS**: Business impact focus, not technical details

5. **BLOCKERS**: Count of must-resolve items before proceeding

6. **KEY DECISION NEEDED**: What specific decision(s) does the executive need to make?

Be concise. Executives need numbers and clear recommendations, not technical details."""

        response = await llm.ainvoke(exec_prompt)

        return json.dumps({
            "status": "success",
            "brief_type": "executive_summary",
            "includes_recommendation": include_recommendation,
            "summary": response.content,
            "data_quality": {
                "assumptions_count": len(critical_assumptions),
                "risks_identified": len(key_risks),
                "open_questions": len(open_questions)
            }
        })
    except Exception as e:
        logger.error(f"Error in prepare_executive_summary tool: {str(e)}")
        return json.dumps({"status": "error", "message": str(e)})


@tool
async def get_technical_deep_dive(component: str = None) -> str:
    """
    Get technical architecture details with trade-offs and risks for architects.
    Explains WHY decisions were made, alternatives considered, and what could go wrong.

    Args:
        component: Optional specific component to focus on (e.g., 'database', 'auth', 'api')
    """
    from database_scripts import get_summary_report
    from langchain_openai import ChatOpenAI
    from config import settings

    try:
        report = await get_summary_report(tool_context.chat_history_id, tool_context.db)

        if not report or not report.summary_report:
            return json.dumps({
                "status": "error",
                "message": "No report found for technical deep dive."
            })

        summary = report.summary_report
        report_content = report.report_content if report.report_content else ""

        # Extract architecture-related data
        recommended_arch = summary.get("recommended_architecture", {}) if isinstance(summary, dict) else {}
        alternatives = summary.get("alternative_architectures", []) if isinstance(summary, dict) else []
        critical_assumptions = summary.get("critical_assumptions", []) if isinstance(summary, dict) else []
        key_risks = summary.get("key_risks", []) if isinstance(summary, dict) else []

        # Use LLM for deep dive analysis
        llm = ChatOpenAI(
            model=settings.GENERATING_REPORT_MODEL,
            api_key=settings.OPENAI_CHATGPT,
            temperature=0.3
        )

        tech_prompt = f"""Create a technical deep-dive analysis for a Solution Architect.

REPORT CONTENT:
{str(report_content)[:8000]}

ARCHITECTURE DATA:
- Recommended: {json.dumps(recommended_arch)}
- Alternatives Considered: {json.dumps(alternatives)}
- Assumptions: {json.dumps(critical_assumptions)}
- Risks: {json.dumps(key_risks)}

{f'FOCUS COMPONENT: {component}' if component else 'Cover the overall architecture'}

Create a technical analysis with:

1. **CHOSEN ARCHITECTURE**: Brief overview of what was selected

2. **WHY THIS OVER ALTERNATIVES**: For each rejected alternative, explain why it was rejected

3. **TRADE-OFFS ACCEPTED**: What compromises were made and why they're acceptable

4. **CRITICAL ASSUMPTIONS**: Technical assumptions that underpin the design

5. **FAILURE MODES TO WATCH**: What could break, how to detect it, how to recover

6. **SCALABILITY ANALYSIS**: Will this work at target scale? What's the ceiling?

7. **TECH DEBT RISKS**: What will be hard to change later?

Be specific and technical. Architects need depth, not summaries."""

        response = await llm.ainvoke(tech_prompt)

        return json.dumps({
            "status": "success",
            "analysis_type": "technical_deep_dive",
            "component_focus": component,
            "analysis": response.content,
            "source_data": {
                "has_recommended_arch": bool(recommended_arch),
                "alternatives_count": len(alternatives),
                "assumptions_count": len(critical_assumptions),
                "risks_count": len(key_risks)
            }
        })
    except Exception as e:
        logger.error(f"Error in get_technical_deep_dive tool: {str(e)}")
        return json.dumps({"status": "error", "message": str(e)})


@tool
async def get_implementation_gotchas() -> str:
    """
    Get implementation-specific warnings and gotchas for developers.
    Includes: unclear requirements, risky assumptions, known technology issues,
    critical dependencies, and specific test scenarios.
    """
    from database_scripts import get_summary_report
    from langchain_openai import ChatOpenAI
    from config import settings

    try:
        report = await get_summary_report(tool_context.chat_history_id, tool_context.db)

        if not report or not report.summary_report:
            return json.dumps({
                "status": "error",
                "message": "No report found for implementation analysis."
            })

        summary = report.summary_report
        report_content = report.report_content if report.report_content else ""

        # Extract relevant data
        critical_assumptions = summary.get("critical_assumptions", []) if isinstance(summary, dict) else []
        key_risks = summary.get("key_risks", []) if isinstance(summary, dict) else []
        open_questions = summary.get("open_questions_for_client", []) if isinstance(summary, dict) else []

        # Try to get presales blind spots
        blind_spots = None
        try:
            from database_scripts import get_presales_by_chat_history
            presales = await get_presales_by_chat_history(tool_context.chat_history_id, tool_context.db)
            if presales:
                blind_spots = getattr(presales, 'blind_spots', None)
        except Exception:
            pass

        # Use LLM to synthesize gotchas
        llm = ChatOpenAI(
            model=settings.GENERATING_REPORT_MODEL,
            api_key=settings.OPENAI_CHATGPT,
            temperature=0.3
        )

        gotcha_prompt = f"""Create a developer onboarding brief with implementation gotchas.

REPORT CONTENT:
{str(report_content)[:8000]}

STRUCTURED DATA:
- Assumptions (may affect implementation): {json.dumps(critical_assumptions)}
- Risks (may cause issues): {json.dumps(key_risks)}
- Open Questions (unclear requirements): {json.dumps(open_questions)}
{f'- Blind Spots (hidden complexities): {json.dumps(blind_spots)}' if blind_spots else ''}

Create a developer brief with:

1. **GOTCHAS TO KNOW** - Things that WILL cause problems if not addressed early. For each:
   - What's the issue
   - Why it matters
   - Suggested workaround

2. **UNCLEAR REQUIREMENTS** - Requirements that need clarification before coding. Include:
   - The requirement
   - What's unclear
   - Who to ask

3. **RISKY ASSUMPTIONS** - Assumptions in the design that could invalidate your code:
   - The assumption
   - Impact if wrong
   - How to validate

4. **DEPENDENCIES** - What you're waiting on:
   - What's needed
   - From whom
   - By when

5. **TEST THESE SCENARIOS** - Specific edge cases and error conditions to test

Be specific and actionable. Developers need details, not high-level summaries."""

        response = await llm.ainvoke(gotcha_prompt)

        return json.dumps({
            "status": "success",
            "brief_type": "implementation_gotchas",
            "gotchas": response.content,
            "data_sources": {
                "assumptions_count": len(critical_assumptions),
                "risks_count": len(key_risks),
                "open_questions_count": len(open_questions),
                "has_blind_spots": blind_spots is not None
            }
        })
    except Exception as e:
        logger.error(f"Error in get_implementation_gotchas tool: {str(e)}")
        return json.dumps({"status": "error", "message": str(e)})


@tool
async def get_project_blind_spots() -> str:
    """
    Get hidden complexities and risks identified during project analysis.
    Includes: blind spots, technology risks, red flags, P1 blockers, and critical unknowns.
    These are issues that might not be obvious but could derail the project.
    """
    from database_scripts import get_summary_report

    try:
        # First try to get presales analysis (has richer blind spot data)
        presales_data = None
        try:
            from database_scripts import get_presales_by_chat_history
            presales = await get_presales_by_chat_history(tool_context.chat_history_id, tool_context.db)
            if presales:
                presales_data = {
                    "blind_spots": getattr(presales, 'blind_spots', None),
                    "technology_risks": getattr(presales, 'technology_risks', None),
                    "red_flags": getattr(presales, 'red_flags', None),
                    "p1_blockers": getattr(presales, 'p1_blockers', None),
                    "critical_unknowns": getattr(presales, 'critical_unknowns', None)
                }
        except Exception:
            pass

        # Also get from main report
        report = await get_summary_report(tool_context.chat_history_id, tool_context.db)

        if not report and not presales_data:
            return json.dumps({
                "status": "error",
                "message": "No report or presales analysis found."
            })

        result = {
            "status": "success",
            "blind_spots_source": "presales" if presales_data else "report"
        }

        if presales_data:
            result["presales_insights"] = presales_data

        if report and report.summary_report:
            summary = report.summary_report
            if isinstance(summary, dict):
                result["report_insights"] = {
                    "critical_assumptions": summary.get("critical_assumptions", []),
                    "key_risks": summary.get("key_risks", []),
                    "open_questions": summary.get("open_questions_for_client", [])
                }

        return json.dumps(result)
    except Exception as e:
        logger.error(f"Error in get_project_blind_spots tool: {str(e)}")
        return json.dumps({"status": "error", "message": str(e)})


@tool
async def get_project_insights(insight_type: str) -> str:
    """
    Get specific project insights with context and implications.

    Args:
        insight_type: Type of insight to extract:
            - "assumptions": Critical assumptions with impact if wrong
            - "risks": Key risks with mitigations and residual risk
            - "alternatives": Alternative approaches considered and why rejected
            - "questions": Open questions for client with priority and impact
            - "mvp_vs_production": Differences between MVP and full production
            - "blockers": What must be resolved before proceeding
    """
    from database_scripts import get_summary_report

    VALID_TYPES = ["assumptions", "risks", "alternatives", "questions", "mvp_vs_production", "blockers"]

    if insight_type not in VALID_TYPES:
        return json.dumps({
            "status": "error",
            "message": f"Invalid insight_type. Must be one of: {', '.join(VALID_TYPES)}"
        })

    try:
        report = await get_summary_report(tool_context.chat_history_id, tool_context.db)

        if not report or not report.summary_report:
            return json.dumps({
                "status": "error",
                "message": "No report found."
            })

        summary = report.summary_report
        report_content = report.report_content if report.report_content else ""

        result = {
            "status": "success",
            "insight_type": insight_type
        }

        if isinstance(summary, dict):
            if insight_type == "assumptions":
                result["data"] = summary.get("critical_assumptions", [])
                result["interpretation"] = "These are assumptions made during analysis. If any are wrong, the architecture/estimates may need revision."

            elif insight_type == "risks":
                result["data"] = summary.get("key_risks", [])
                result["interpretation"] = "These risks have been identified with mitigations. Monitor and revisit during implementation."

            elif insight_type == "alternatives":
                result["data"] = summary.get("alternative_architectures", [])
                result["interpretation"] = "These alternatives were considered but rejected. Useful context for stakeholder discussions."

            elif insight_type == "questions":
                result["data"] = summary.get("open_questions_for_client", [])
                result["interpretation"] = "These questions need client answers. Each affects scope, timeline, or architecture."

            elif insight_type == "mvp_vs_production":
                # This needs to be extracted from report content
                mvp_section = ""
                if "MVP" in report_content and "Production" in report_content:
                    # Try to find the MVP vs Production section
                    lines = report_content.split('\n')
                    capture = False
                    for line in lines:
                        if "mvp" in line.lower() and "production" in line.lower():
                            capture = True
                        if capture:
                            mvp_section += line + "\n"
                            if len(mvp_section) > 2000:
                                break
                result["data"] = mvp_section if mvp_section else "MVP vs Production comparison not found in report"
                result["interpretation"] = "Key differences between MVP scope and full production deployment."

            elif insight_type == "blockers":
                # Combine assumptions that are unvalidated + high-impact risks
                blockers = []
                for assumption in summary.get("critical_assumptions", []):
                    if isinstance(assumption, dict) and assumption.get("impact"):
                        blockers.append({
                            "type": "assumption",
                            "item": assumption.get("assumption", str(assumption)),
                            "impact": assumption.get("impact", "Unknown impact")
                        })
                for risk in summary.get("key_risks", []):
                    if isinstance(risk, dict):
                        blockers.append({
                            "type": "risk",
                            "item": risk.get("risk", str(risk)),
                            "mitigation": risk.get("mitigation", "No mitigation specified")
                        })
                result["data"] = blockers
                result["interpretation"] = "Items that should be resolved or have mitigation plans before proceeding."

        return json.dumps(result)
    except Exception as e:
        logger.error(f"Error in get_project_insights tool: {str(e)}")
        return json.dumps({"status": "error", "message": str(e)})


@tool
async def find_duplicate_changes(similarity_threshold: float = 0.6) -> str:
    """
    Find pending changes that are similar or duplicates of each other.
    Use this when user wants to clean up or consolidate their changes.
    Returns groups of similar changes that could potentially be merged.

    Args:
        similarity_threshold: Similarity threshold (0-1) for considering changes as duplicates. Default 0.6
    """
    from database_scripts import get_pending_changes as db_get_pending
    from database_scripts import find_duplicate_changes as db_find_duplicates

    try:
        # First get pending changes
        changes = await db_get_pending(tool_context.chat_history_id, tool_context.db)

        if not changes or len(changes) < 2:
            return json.dumps({
                "status": "success",
                "message": "Need at least 2 changes to find duplicates",
                "duplicates": []
            })

        # find_duplicate_changes takes the list, not chat_history_id
        duplicates = await db_find_duplicates(changes, similarity_threshold)

        if not duplicates:
            return json.dumps({
                "status": "success",
                "message": "No duplicate changes found",
                "duplicates": []
            })

        return json.dumps({
            "status": "success",
            "duplicate_groups": duplicates,
            "recommendation": "You can merge similar changes using the merge_pending_changes tool"
        })
    except Exception as e:
        logger.error(f"Error in find_duplicate_changes tool: {str(e)}")
        return json.dumps({"status": "error", "message": str(e)})


@tool
async def detect_conflicts() -> str:
    """
    Detect conflicting pending changes that modify the same report sections
    in incompatible ways (e.g., one says 'use AWS' and another says 'use Azure').
    Use this before regenerating to warn users about potential conflicts.
    """
    from database_scripts import get_pending_changes as db_get_pending
    from database_scripts import detect_conflicts as db_detect_conflicts

    try:
        # Get pending changes first
        changes = await db_get_pending(tool_context.chat_history_id, tool_context.db)

        if not changes or len(changes) < 2:
            return json.dumps({
                "status": "success",
                "message": "No conflicts possible with fewer than 2 changes",
                "conflicts": []
            })

        # detect_conflicts is sync and takes the list
        conflicts = db_detect_conflicts(changes)

        if not conflicts:
            return json.dumps({
                "status": "success",
                "message": "No conflicts detected. All changes are compatible.",
                "conflicts": []
            })

        return json.dumps({
            "status": "success",
            "conflicts": conflicts,
            "recommendation": "Please resolve conflicts before regenerating. You can remove or edit conflicting changes."
        })
    except Exception as e:
        logger.error(f"Error in detect_conflicts tool: {str(e)}")
        return json.dumps({"status": "error", "message": str(e)})


@tool
async def get_report_versions(limit: int = 10) -> str:
    """
    Get the history of report versions with changelog summaries.
    Use when user asks about previous versions or wants to see what changed.

    Args:
        limit: Maximum number of versions to return (default: 10)
    """
    from database_scripts import get_all_report_versions

    try:
        versions = await get_all_report_versions(tool_context.chat_history_id, tool_context.db)

        if not versions:
            return json.dumps({
                "status": "success",
                "message": "No report versions found yet",
                "versions": []
            })

        # Limit and simplify version info with changelog data
        limited_versions = versions[:limit]
        simplified = []
        for v in limited_versions:
            version_info = {
                "version_id": v.get("version_id") or v.get("id"),
                "version_number": v.get("version"),
                "created_at": str(v.get("created_at", "")),
                "has_pending_changes": bool(v.get("pending_changes")),
                # Changelog tracking fields
                "changelog_summary": v.get("changelog_summary") or ("Initial report generation" if v.get("version") == 1 else "No changelog available"),
                "changes_applied_count": len(v.get("changes_applied", [])) if v.get("changes_applied") else 0
            }
            simplified.append(version_info)

        return json.dumps({
            "status": "success",
            "versions": simplified,
            "total_count": len(versions)
        })
    except Exception as e:
        logger.error(f"Error in get_report_versions tool: {str(e)}")
        return json.dumps({"status": "error", "message": str(e)})


@tool
async def compare_report_versions(
    version_a: int,
    version_b: int = None,
    include_content: bool = False
) -> str:
    """
    Compare two report versions to understand what changed between them.
    Use when user asks about differences between versions, how architecture evolved,
    or wants to understand why certain decisions changed.

    Args:
        version_a: First version number to compare
        version_b: Second version number (defaults to latest if not provided)
        include_content: If True, includes full executive summaries. If False, just changelog info.
    """
    from database_scripts import get_report_version_by_number, get_report_diff, get_all_report_versions

    try:
        chat_history_id = tool_context.chat_history_id
        db = tool_context.db

        # Get all versions to determine latest if version_b not provided
        all_versions = await get_all_report_versions(chat_history_id, db)
        if not all_versions:
            return json.dumps({
                "status": "error",
                "message": "No report versions found"
            })

        latest_version = max(v.get("version", 1) for v in all_versions)

        # Default version_b to latest if not provided
        if version_b is None:
            version_b = latest_version

        # Ensure version_a < version_b
        if version_a > version_b:
            version_a, version_b = version_b, version_a

        # Validate versions exist
        if version_a < 1 or version_b > latest_version:
            return json.dumps({
                "status": "error",
                "message": f"Invalid version numbers. Available versions: 1 to {latest_version}"
            })

        # Get version details
        try:
            ver_a_record = await get_report_version_by_number(chat_history_id, version_a, db)
            ver_b_record = await get_report_version_by_number(chat_history_id, version_b, db)
        except Exception as e:
            return json.dumps({
                "status": "error",
                "message": f"Could not retrieve version details: {str(e)}"
            })

        # Get diff stats
        try:
            diff_result = await get_report_diff(chat_history_id, version_a, version_b, db)
            diff_stats = diff_result.get("stats", {})
        except Exception as e:
            logger.warning(f"Could not compute diff: {str(e)}")
            diff_stats = {}

        # Build comparison response
        comparison = {
            "version_a": {
                "version_number": version_a,
                "created_at": ver_a_record.get("created_at"),
                "changelog_summary": ver_a_record.get("changelog_summary") or ("Initial report generated from document analysis." if version_a == 1 else "No changelog available (created before tracking enabled)"),
                "changes_applied": ver_a_record.get("changes_applied") or [],
                "is_initial": version_a == 1
            },
            "version_b": {
                "version_number": version_b,
                "created_at": ver_b_record.get("created_at"),
                "changelog_summary": ver_b_record.get("changelog_summary") or "No changelog available",
                "changes_applied": ver_b_record.get("changes_applied") or [],
                "parent_version_id": ver_b_record.get("parent_version_id")
            },
            "diff_stats": diff_stats
        }

        # Include executive summaries if requested
        if include_content:
            summary_a = ver_a_record.get("summary_report", {})
            summary_b = ver_b_record.get("summary_report", {})
            comparison["executive_summaries"] = {
                "version_a": summary_a.get("executive_summary", "") if isinstance(summary_a, dict) else "",
                "version_b": summary_b.get("executive_summary", "") if isinstance(summary_b, dict) else ""
            }

        return json.dumps({
            "status": "success",
            "comparison": comparison
        })

    except Exception as e:
        logger.error(f"Error in compare_report_versions tool: {str(e)}")
        return json.dumps({"status": "error", "message": str(e)})


# ============= WRITE TOOLS =============

@tool
async def add_pending_change(
    user_request: str,
    target_section: str = "general",
    change_type: str = "modify"
) -> str:
    """
    Add a new pending change/suggestion to modify the report.
    This queues the change for the next report regeneration.

    Args:
        user_request: The user's request describing what change they want (e.g., "Use Redis instead of PostgreSQL for caching")
        target_section: The report section this targets: executive_summary, tech_stack, team_structure, timeline, risks, recommendations, or general
        change_type: Type of change: add (new content), modify (change existing), remove (delete content), replace (swap content)
    """
    from database_scripts import add_pending_change as db_add_change
    from database_scripts import record_transaction

    try:
        change_data = {
            "user_request": user_request,
            "target_section": target_section,
            "type": f"modify_{target_section}" if target_section != "general" else "modify_architecture",
            "change_type": change_type
        }

        result = await db_add_change(tool_context.chat_history_id, change_data, tool_context.db)

        # Record transaction for undo capability
        if result.get("status") == "success":
            await record_transaction(
                chat_history_id=tool_context.chat_history_id,
                action_type="add_change",
                action_data={
                    "change_id": result.get("change_id"),
                    "user_request": user_request,
                    "change_data": change_data
                },
                description=f"Added {result.get('change_id')}: {user_request[:50]}...",
                db=tool_context.db
            )

        return json.dumps(result)
    except Exception as e:
        logger.error(f"Error in add_pending_change tool: {str(e)}")
        return json.dumps({"status": "error", "message": str(e)})


@tool
async def remove_pending_change(change_id: str) -> str:
    """
    Remove a specific pending change by its ID (e.g., CHG-001).
    Use when user wants to undo or delete a specific change they made.

    Args:
        change_id: The ID of the change to remove (e.g., 'CHG-001', 'CHG-002')
    """
    from database_scripts import remove_pending_change as db_remove
    from database_scripts import get_pending_changes as db_get_pending
    from database_scripts import record_transaction

    try:
        # Get the change data before removal for transaction record
        changes = await db_get_pending(tool_context.chat_history_id, tool_context.db)
        change_to_remove = next((c for c in changes if c.get("id") == change_id), None)

        if not change_to_remove:
            return json.dumps({
                "status": "error",
                "message": f"Change {change_id} not found. Use get_pending_changes to see available changes."
            })

        result = await db_remove(tool_context.chat_history_id, change_id, tool_context.db)

        if result.get("status") == "success":
            await record_transaction(
                chat_history_id=tool_context.chat_history_id,
                action_type="remove_change",
                action_data={"change_id": change_id, "removed_change": change_to_remove},
                description=f"Removed {change_id}",
                db=tool_context.db
            )

        return json.dumps(result)
    except Exception as e:
        logger.error(f"Error in remove_pending_change tool: {str(e)}")
        return json.dumps({"status": "error", "message": str(e)})


@tool
async def remove_last_pending_change() -> str:
    """
    Remove the most recently added pending change.
    Use when user says 'undo', 'take that back', or 'remove the last one' without specifying which change.
    """
    from database_scripts import remove_last_pending_change as db_remove_last
    from database_scripts import record_transaction

    try:
        result = await db_remove_last(tool_context.chat_history_id, tool_context.db)

        if result.get("status") == "success":
            removed = result.get("removed_change", {})
            await record_transaction(
                chat_history_id=tool_context.chat_history_id,
                action_type="undo_last",
                action_data={"removed_change": removed},
                description=f"Undid last change: {removed.get('id', 'unknown')}",
                db=tool_context.db
            )

        return json.dumps(result)
    except Exception as e:
        logger.error(f"Error in remove_last_pending_change tool: {str(e)}")
        return json.dumps({"status": "error", "message": str(e)})


@tool
async def clear_all_pending_changes(confirmed: bool = False) -> str:
    """
    Remove ALL pending changes and start fresh.
    WARNING: This is a DESTRUCTIVE operation. Always ask the user to confirm before calling with confirmed=True.

    Args:
        confirmed: Must be True to execute. If False, returns a confirmation request message.
    """
    from database_scripts import clear_pending_changes, get_pending_changes as db_get_pending
    from database_scripts import record_transaction

    try:
        # Always get current changes first
        changes = await db_get_pending(tool_context.chat_history_id, tool_context.db)

        if not changes:
            return json.dumps({
                "status": "success",
                "message": "No pending changes to clear. Already empty.",
                "cleared_count": 0
            })

        if not confirmed:
            return json.dumps({
                "status": "needs_confirmation",
                "message": f"This will permanently remove ALL {len(changes)} pending changes. Ask the user: 'Are you sure you want to clear all {len(changes)} pending changes?'",
                "count": len(changes),
                "changes_to_clear": [{"id": c.get("id"), "request": c.get("user_request", "")[:50]} for c in changes]
            })

        # Record before clearing for undo capability
        await record_transaction(
            chat_history_id=tool_context.chat_history_id,
            action_type="clear_all",
            action_data={"cleared_changes": changes, "count": len(changes)},
            description=f"Cleared {len(changes)} pending changes",
            db=tool_context.db
        )

        result = await clear_pending_changes(tool_context.chat_history_id, tool_context.db)

        if result.get("status") == "success":
            return json.dumps({
                "status": "success",
                "message": f"Successfully cleared {len(changes)} pending changes. Starting fresh.",
                "cleared_count": len(changes)
            })

        return json.dumps(result)
    except Exception as e:
        logger.error(f"Error in clear_all_pending_changes tool: {str(e)}")
        return json.dumps({"status": "error", "message": str(e)})


@tool
async def merge_pending_changes(change_ids: List[str], merged_description: Optional[str] = None) -> str:
    """
    Merge multiple pending changes into a single consolidated change.
    Use when user wants to combine similar or related changes.

    Args:
        change_ids: List of change IDs to merge (e.g., ['CHG-001', 'CHG-002']). Requires at least 2.
        merged_description: Optional custom description for the merged change. If not provided, descriptions will be combined.
    """
    from database_scripts import merge_pending_changes as db_merge
    from database_scripts import get_pending_changes as db_get_pending
    from database_scripts import record_transaction

    try:
        if len(change_ids) < 2:
            return json.dumps({
                "status": "error",
                "message": "Need at least 2 change IDs to merge"
            })

        # Get current changes to build merged content if not provided
        changes = await db_get_pending(tool_context.chat_history_id, tool_context.db)
        changes_to_merge = [c for c in changes if c.get("id") in change_ids]

        if len(changes_to_merge) < 2:
            found_ids = [c.get("id") for c in changes_to_merge]
            return json.dumps({
                "status": "error",
                "message": f"Could not find all changes. Found: {found_ids}, requested: {change_ids}"
            })

        # Build merged content if not provided
        if not merged_description:
            merged_description = " AND ".join([
                c.get("user_request", "") for c in changes_to_merge
            ])

        result = await db_merge(
            tool_context.chat_history_id,
            change_ids,
            merged_description,
            tool_context.db
        )

        if result.get("status") == "success":
            await record_transaction(
                chat_history_id=tool_context.chat_history_id,
                action_type="merge_changes",
                action_data={
                    "merged_ids": change_ids,
                    "new_change_id": result.get("new_change", {}).get("id"),
                    "original_changes": changes_to_merge
                },
                description=f"Merged {len(change_ids)} changes into {result.get('new_change', {}).get('id')}",
                db=tool_context.db
            )

        return json.dumps(result)
    except Exception as e:
        logger.error(f"Error in merge_pending_changes tool: {str(e)}")
        return json.dumps({"status": "error", "message": str(e)})


@tool
async def update_pending_change(change_id: str, new_description: str) -> str:
    """
    Edit/update an existing pending change's description.
    Use when user wants to modify what a change says without removing and re-adding it.

    Args:
        change_id: The ID of the change to update (e.g., 'CHG-001')
        new_description: The new description/request for the change
    """
    from database_scripts import update_pending_change as db_update
    from database_scripts import get_pending_changes as db_get_pending
    from database_scripts import record_transaction

    try:
        # Get original change for transaction record
        changes = await db_get_pending(tool_context.chat_history_id, tool_context.db)
        original_change = next((c for c in changes if c.get("id") == change_id), None)

        if not original_change:
            return json.dumps({
                "status": "error",
                "message": f"Change {change_id} not found"
            })

        # update_pending_change takes a dict of updates
        updates = {"user_request": new_description}
        result = await db_update(tool_context.chat_history_id, change_id, updates, tool_context.db)

        if result.get("status") == "success":
            await record_transaction(
                chat_history_id=tool_context.chat_history_id,
                action_type="update_change",
                action_data={
                    "change_id": change_id,
                    "old_description": original_change.get("user_request"),
                    "new_description": new_description
                },
                description=f"Updated {change_id}",
                db=tool_context.db
            )

        return json.dumps(result)
    except Exception as e:
        logger.error(f"Error in update_pending_change tool: {str(e)}")
        return json.dumps({"status": "error", "message": str(e)})


# ============= REPORT TOOLS =============

@tool
async def regenerate_report(include_changes: bool = True) -> str:
    """
    Regenerate the report with all pending changes applied as mandatory constraints.
    This runs the full 9-agent analysis pipeline with changes injected as constraints.

    The process:
    1. Checks for pending changes (requires at least 1)
    2. Detects conflicts between changes (provides guidance to resolve if found)
    3. Retrieves document, presales data, Q&A context from DB
    4. Runs full 9-agent pipeline with changes as MANDATORY ARCHITECTURAL CONSTRAINTS
    5. Creates new report version
    6. Updates vector DB with new report
    7. Clears pending changes (marks as applied)

    This takes 2-3 minutes to complete.

    Args:
        include_changes: Whether to include pending changes (default: true)
    """
    from database_scripts import (
        get_pending_changes as db_get_pending,
        get_regeneration_context,
        detect_conflicts as db_detect_conflicts,
        create_new_report_version,
        clear_pending_changes,
        record_transaction
    )
    from agents.agentic_workflow import run_pipeline_with_constraints, main_report_summary, generate_changelog_summary
    from utils.router_llm import generate_conflict_resolution
    from vectordb.chunking import chunk_text
    from vectordb.vector_db import create_embeddings
    from config import settings
    import time

    start_time = time.time()
    chat_history_id = tool_context.chat_history_id
    user_id = tool_context.user_id
    db = tool_context.db

    # Validate user_id
    if not user_id:
        return json.dumps({
            "status": "error",
            "message": "Unable to identify user. Please try again.",
            "action": "missing_user_id"
        })

    try:
        # Step 1: GET PENDING CHANGES
        pending_changes = await db_get_pending(chat_history_id, db)

        if not pending_changes or len(pending_changes) == 0:
            return json.dumps({
                "status": "error",
                "message": "There are no pending changes to apply. Your report is up to date.\n\nYou can suggest modifications like:\n- 'Use PostgreSQL instead of MongoDB'\n- 'Add real-time notifications feature'\n- 'Consider microservices architecture'\n\nI'll track them as pending changes, and you can regenerate when ready.",
                "action": "no_changes"
            })

        # Step 2: CHECK FOR CONFLICTS
        conflicts = db_detect_conflicts(pending_changes)  # sync function

        if conflicts:
            # Generate helpful conflict resolution message
            try:
                conflict_msg = await generate_conflict_resolution(conflicts, pending_changes)
                return json.dumps({
                    "status": "conflicts_detected",
                    "message": conflict_msg,
                    "conflicts": conflicts,
                    "action": "resolve_conflicts",
                    "recommendation": "Use remove_pending_change(change_id) or update_pending_change(change_id, new_description) to resolve conflicts, then try regenerating again."
                })
            except Exception as e:
                # Fallback to simple conflict message
                logger.warning(f"Could not generate conflict resolution message: {str(e)}")
                conflict_list = "\n".join([
                    f"- {c.get('description', 'Unknown conflict')}"
                    for c in conflicts
                ])
                return json.dumps({
                    "status": "conflicts_detected",
                    "message": f"Found {len(conflicts)} conflict(s) in your pending changes:\n\n{conflict_list}\n\nPlease resolve these before regenerating. You can use remove_pending_change('CHG-XXX') to remove a conflicting change or update_pending_change() to modify it.",
                    "conflicts": conflicts,
                    "action": "resolve_conflicts"
                })

        # Step 3: GET FULL REGENERATION CONTEXT (document, presales data, Q&A, etc.)
        try:
            regen_context = await get_regeneration_context(chat_history_id, user_id, db)
        except Exception as e:
            logger.error(f"Failed to get regeneration context: {str(e)}")
            return json.dumps({
                "status": "error",
                "message": "Could not retrieve the necessary context for regeneration. Please try again.",
                "action": "context_error"
            })

        # Step 4: RUN FULL 9-AGENT PIPELINE WITH CONSTRAINTS
        try:
            # Document needs to be in list format for pipeline
            document_chunks = [regen_context.get("document_text", "")]

            # Build presales context dict with all available data
            presales_context = {
                "scanned_requirements": regen_context.get("scanned_requirements"),
                "blind_spots": regen_context.get("blind_spots"),
                "assumptions_list": regen_context.get("assumptions_list", []),
                "questions_and_answers": regen_context.get("questions_and_answers", []),
                "additional_context": regen_context.get("additional_context", ""),
                "user_answers": regen_context.get("user_answers", {})
            }

            logger.info(
                f"Starting regeneration for chat_history_id: {chat_history_id} with "
                f"{len(pending_changes)} changes, {len(presales_context.get('questions_and_answers', []))} Q&A pairs"
            )

            result = await run_pipeline_with_constraints(
                document=document_chunks,
                pending_changes=pending_changes,
                presales_context=presales_context,
                timeout=settings.PIPELINE_TIMEOUT or 600  # 10 min for full pipeline
            )

            if result.get("error"):
                raise Exception(result["error"])

            regenerated_report = result["report"]
            processing_time = result.get("processing_time", time.time() - start_time)
            logger.info(f"Full pipeline completed in {processing_time:.2f}s with {len(pending_changes)} constraints")

        except Exception as e:
            logger.error(f"Report generation failed: {str(e)}")
            return json.dumps({
                "status": "error",
                "message": f"Report generation encountered an error: {str(e)}\n\nPlease try again. If the problem persists, try removing some pending changes and regenerating.",
                "action": "pipeline_error"
            })

        # Step 5: GENERATE REPORT SUMMARY
        try:
            new_version_number = regen_context.get("current_version", 0) + 1
            summary_report = await main_report_summary(regenerated_report, new_version_number)
        except Exception as e:
            logger.error(f"Failed to generate report summary: {str(e)}")
            summary_report = {"version": f"v{new_version_number}", "error": "Summary generation failed"}

        # Step 5.5: GENERATE CHANGELOG SUMMARY
        changelog_summary = None
        parent_version_id = None
        try:
            # Get previous version's summary for comparison
            previous_summary = regen_context.get("previous_summary", {})
            parent_version_id = regen_context.get("previous_version_id")
            previous_version_number = regen_context.get("current_version", 0)

            if previous_summary:
                previous_exec_summary = previous_summary.get("executive_summary", "") if isinstance(previous_summary, dict) else str(previous_summary)
                new_exec_summary = summary_report.get("executive_summary", "") if isinstance(summary_report, dict) else str(summary_report)

                changelog_summary = await generate_changelog_summary(
                    previous_summary=previous_exec_summary,
                    new_summary=new_exec_summary,
                    changes_applied=pending_changes,
                    previous_version=previous_version_number,
                    new_version=new_version_number
                )
                logger.info(f"Generated changelog summary for v{previous_version_number} -> v{new_version_number}")
            else:
                changelog_summary = f"Version {new_version_number} created with {len(pending_changes)} change(s) applied."
        except Exception as e:
            logger.warning(f"Failed to generate changelog summary (non-fatal): {str(e)}")
            changelog_summary = f"Version {new_version_number} created with {len(pending_changes)} change(s) applied."

        # Step 6: CREATE NEW REPORT VERSION IN DB
        try:
            version_result = await create_new_report_version(
                chat_history_id=chat_history_id,
                user_id=user_id,
                report_content=regenerated_report,
                summary_report=summary_report,
                changes_applied=pending_changes,
                db=db,
                changelog_summary=changelog_summary,
                parent_version_id=parent_version_id
            )
            new_version = version_result.get("version_number", new_version_number)
        except Exception as e:
            logger.error(f"Failed to create new report version: {str(e)}")
            return json.dumps({
                "status": "partial_success",
                "message": f"Report was generated but couldn't be saved: {str(e)}\n\nPlease try again.",
                "action": "save_error",
                "report_content": regenerated_report  # Include report even if save failed
            })

        # Step 7: UPDATE VECTOR DB (non-fatal if fails)
        try:
            report_chunks = await chunk_text(regenerated_report, chunk_size=1000, chunk_overlap=200)
            await create_embeddings(
                texts=report_chunks,
                model=settings.EMBEDDING_MODEL,
                chat_history_id=chat_history_id
            )
            logger.info(f"Updated vector DB with {len(report_chunks)} chunks")
        except Exception as e:
            logger.warning(f"Failed to update vector DB (non-fatal): {str(e)}")

        # Step 8: CLEAR PENDING CHANGES (non-fatal if fails)
        try:
            await clear_pending_changes(chat_history_id, db)
            logger.info(f"Cleared {len(pending_changes)} pending changes after regeneration")
        except Exception as e:
            logger.warning(f"Failed to clear pending changes (non-fatal): {str(e)}")

        # Step 9: RECORD TRANSACTION
        try:
            await record_transaction(
                chat_history_id=chat_history_id,
                action_type="regenerate_report",
                action_data={
                    "changes_applied": len(pending_changes),
                    "new_version": new_version,
                    "processing_time": processing_time
                },
                description=f"Regenerated report v{new_version} with {len(pending_changes)} changes",
                db=db
            )
        except Exception as e:
            logger.warning(f"Failed to record transaction (non-fatal): {str(e)}")

        # Step 10: BUILD SUCCESS RESPONSE
        changes_summary = "\n".join([
            f"- {c.get('id', 'CHG-?')}: {c.get('user_request', '')[:60]}..."
            for c in pending_changes[:5]
        ])
        if len(pending_changes) > 5:
            changes_summary += f"\n- ... and {len(pending_changes) - 5} more"

        return json.dumps({
            "status": "success",
            "message": f"**Report Regenerated Successfully** (Version {new_version})\n\nApplied {len(pending_changes)} change(s):\n{changes_summary}\n\nThe report has been updated with all your requested modifications.",
            "action": "report_regenerated",
            "version_number": new_version,
            "changes_applied": len(pending_changes),
            "processing_time": f"{processing_time:.1f} seconds",
            "report_content": regenerated_report,
            "summary": summary_report.get("executive_summary", "")[:500] if isinstance(summary_report, dict) else ""
        })

    except Exception as e:
        logger.error(f"Unexpected error in regenerate_report: {str(e)}")
        return json.dumps({
            "status": "error",
            "message": f"An unexpected error occurred: {str(e)}",
            "action": "unexpected_error"
        })


@tool
async def rollback_report(version_number: int) -> str:
    """
    Rollback to a previous report version by creating a new version with that content.
    The new version becomes the default. History is preserved.
    Vector DB is updated with the rolled-back report content.

    Use get_report_versions() first to see available versions.

    Args:
        version_number: The version number to rollback to (e.g., 1, 2, 3)
    """
    from database_scripts import (
        rollback_to_version,
        set_default_version,
        record_transaction
    )
    from vectordb.chunking import chunk_text
    from vectordb.vector_db import create_embeddings
    from config import settings

    try:
        # Validate user_id
        if not tool_context.user_id:
            return json.dumps({
                "status": "error",
                "message": "Unable to identify user. Please try again."
            })

        # Step 1: Create new version with old content
        result = await rollback_to_version(
            chat_history_id=tool_context.chat_history_id,
            user_id=tool_context.user_id,
            target_version_number=version_number,
            db=tool_context.db
        )

        if result.get("status") != "success":
            return json.dumps(result)

        new_version = result.get("new_version_number")
        report_content = result.get("report_content")

        # Step 2: Set the new rollback version as default
        try:
            await set_default_version(
                chat_history_id=tool_context.chat_history_id,
                user_id=tool_context.user_id,
                version_number=new_version,
                db=tool_context.db
            )
        except Exception as e:
            logger.warning(f"Failed to set default (non-fatal): {str(e)}")

        # Step 3: UPDATE VECTOR DB with rolled-back report content
        # This deletes existing embeddings and creates new ones
        try:
            if report_content:
                # Chunk the report content
                report_chunks = await chunk_text(
                    text=report_content,
                    chunk_size=1000,
                    chunk_overlap=200
                )

                # Create embeddings (this deletes old embeddings first)
                await create_embeddings(
                    texts=report_chunks,
                    model=settings.EMBEDDING_MODEL,
                    chat_history_id=tool_context.chat_history_id
                )
                logger.info(f"Updated vector DB with {len(report_chunks)} chunks for rollback")
        except Exception as e:
            logger.warning(f"Failed to update vector DB (non-fatal): {str(e)}")

        # Step 4: Record transaction for undo
        try:
            await record_transaction(
                chat_history_id=tool_context.chat_history_id,
                action_type="rollback",
                action_data={
                    "original_version": version_number,
                    "new_version": new_version
                },
                description=f"Rolled back to version {version_number} as new version {new_version}",
                db=tool_context.db
            )
        except Exception as e:
            logger.warning(f"Failed to record transaction (non-fatal): {str(e)}")

        return json.dumps({
            "status": "success",
            "message": f"Successfully rolled back to version {version_number}. Created as new version {new_version} (now default). Vector DB updated.",
            "original_version": version_number,
            "new_version_number": new_version,
            "is_default": True,
            "vector_db_updated": True
        })

    except Exception as e:
        logger.error(f"Error in rollback_report tool: {str(e)}")
        return json.dumps({
            "status": "error",
            "message": f"Rollback failed: {str(e)}. Please try again or contact support."
        })


@tool
async def set_default_report(version_number: int) -> str:
    """
    Set a specific version as the default/displayed version without creating a new version.
    Use this to switch which version is shown by default.
    Also updates the vector DB with the selected version's content.

    For full rollback (creating new version with old content), use rollback_report instead.

    Args:
        version_number: The version number to set as default
    """
    from database_scripts import set_default_version, get_report_version_by_number
    from vectordb.chunking import chunk_text
    from vectordb.vector_db import create_embeddings
    from config import settings

    try:
        if not tool_context.user_id:
            return json.dumps({
                "status": "error",
                "message": "Unable to identify user. Please try again."
            })

        # Step 1: Set the version as default
        result = await set_default_version(
            chat_history_id=tool_context.chat_history_id,
            user_id=tool_context.user_id,
            version_number=version_number,
            db=tool_context.db
        )

        if result.get("status") != "success":
            return json.dumps(result)

        # Step 2: Get the report content for vector DB update
        try:
            from database_scripts import get_report_version_content
            report_content = await get_report_version_content(
                tool_context.chat_history_id,
                version_number,
                tool_context.db
            )

            # Step 3: Update vector DB with new default's content
            if report_content:
                report_chunks = await chunk_text(
                    text=report_content,
                    chunk_size=1000,
                    chunk_overlap=200
                )
                await create_embeddings(
                    texts=report_chunks,
                    model=settings.EMBEDDING_MODEL,
                    chat_history_id=tool_context.chat_history_id
                )
                logger.info(f"Updated vector DB for new default version {version_number}")
        except Exception as e:
            logger.warning(f"Failed to update vector DB (non-fatal): {str(e)}")

        return json.dumps({
            "status": "success",
            "message": f"Version {version_number} is now the default version. Vector DB updated.",
            "version_number": version_number,
            "is_default": True
        })

    except Exception as e:
        logger.error(f"Error in set_default_report tool: {str(e)}")
        return json.dumps({
            "status": "error",
            "message": f"Failed to set default: {str(e)}"
        })


# ============= TOOL COLLECTION =============

def get_all_tools() -> list:
    """Return all tools for binding to LLM."""
    return [
        # Read-only tools
        get_pending_changes,
        search_document,
        get_report_section,
        search_report_section,
        get_risks_and_mitigations,
        find_duplicate_changes,
        detect_conflicts,
        get_report_versions,
        compare_report_versions,
        # Optimization & Analysis tools
        suggest_optimization,
        analyze_cost_reduction,
        analyze_timeline_acceleration,
        # Persona-Specific Briefing tools
        prepare_client_meeting_brief,  # PM meeting preparation
        prepare_executive_summary,  # Executive go/no-go briefing
        get_technical_deep_dive,  # Architect technical analysis
        get_implementation_gotchas,  # Developer onboarding
        get_project_blind_spots,  # Hidden complexities and risks
        get_project_insights,  # Structured insight extraction
        # Write tools
        add_pending_change,
        remove_pending_change,
        remove_last_pending_change,
        clear_all_pending_changes,
        merge_pending_changes,
        update_pending_change,
        # Report tools
        regenerate_report,
        rollback_report,
        set_default_report,
    ]


# System prompt for tool-enabled chat
TOOL_SYSTEM_PROMPT = """You are ALIGN IQ, an expert AI assistant for project analysis and technical consulting. You help users understand, refine, and improve their project analysis reports.

## Your Role

You assist diverse stakeholders - business analysts, solution architects, developers, project managers, and executives - during pre-sales and project planning phases. Adapt your communication style based on context clues:

- **Technical users** (mention APIs, databases, code, architecture): Provide detailed technical explanations with specific technology recommendations
- **Business users** (mention costs, timelines, resources, stakeholders): Focus on business impact, risks, and resource implications
- **Executives** (brief questions, strategic focus): Lead with executive summary, key decisions, and recommendations

## CRITICAL: Insight Synthesis (Not Just Data Retrieval)

You are a CONSULTANT, not a search engine. Every response must provide ACTIONABLE INSIGHTS, not just formatted data.

### 1. EXPLAIN THE WHY
Don't just state facts - explain reasoning behind decisions:
- BAD: "Redis is recommended for caching"
- GOOD: "Redis is recommended because your 10K concurrent user requirement needs sub-100ms latency. Database-only would handle ~2K queries/sec, creating a bottleneck."

### 2. SURFACE HIDDEN RISKS
Proactively mention what could go wrong:
- BAD: Answer the question, move on
- GOOD: "This approach has one critical risk: [X]. Here's how to mitigate it..."

### 3. SHOW TRADE-OFFS
Always mention alternatives and why they were rejected:
- BAD: "We chose DynamoDB"
- GOOD: "We chose DynamoDB over PostgreSQL because [X]. PostgreSQL was rejected because [Y]. However, if your requirements change to [Z], reconsider this choice."

### 4. QUANTIFY IMPACT
Use numbers, not vague statements:
- BAD: "This will take some time"
- GOOD: "Estimated 8-12 weeks for MVP, 85% confidence. Production adds 16-20 weeks."

### 5. ANTICIPATE STAKEHOLDER QUESTIONS
Provide ammunition for hard conversations:
- BAD: Answer only what was asked
- GOOD: "If stakeholders challenge this, here's the strongest counterargument: [X]"

### 6. ALWAYS SURFACE KEY INSIGHTS FROM REPORT
When answering ANY question, automatically include relevant:
- **Assumptions** that underpin the answer (from summary_report.critical_assumptions)
- **Risks** related to the topic (from summary_report.key_risks)
- **Open questions** that affect this area (from summary_report.open_questions_for_client)
- **Blind spots** if presales analysis exists (hidden complexities, red flags)

## Your Capabilities

### Document & Report Tools
- **search_document(query)**: Search the uploaded document and report for specific content using semantic search
- **search_report_section(query, section)**: Search within a specific report section for detailed information
- **get_report_section(section)**: Retrieve report sections (executive_summary, tech_stack, team_structure, timeline, risks, recommendations, full_report)
- **get_risks_and_mitigations()**: Get all identified risks with their mitigation strategies
- **get_report_versions()**: View report version history with changelog summaries showing what changed
- **compare_report_versions(version_a, version_b)**: Compare two versions to see detailed differences, changes applied, and implications

### Optimization & Analysis Tools
- **suggest_optimization(constraint_type, details)**: Generate optimization suggestions based on user constraints (budget, timeline, resource, scope)
- **analyze_cost_reduction()**: Identify cost reduction opportunities with trade-offs
- **analyze_timeline_acceleration()**: Identify ways to accelerate the project timeline

### Persona-Specific Briefing Tools
- **prepare_client_meeting_brief(focus_areas)**: Prepare PM meeting brief with blockers, questions for client, risks to communicate, and pushback responses
- **prepare_executive_summary(include_recommendation)**: Executive go/no-go briefing with budget/timeline confidence, top risks, and recommendation
- **get_technical_deep_dive(component)**: Architect analysis with trade-offs, alternatives considered, failure modes, and scalability analysis
- **get_implementation_gotchas()**: Developer onboarding with gotchas, unclear requirements, risky assumptions, and test scenarios
- **get_project_blind_spots()**: Hidden complexities from presales analysis (blind spots, red flags, P1 blockers)
- **get_project_insights(insight_type)**: Extract specific insights (assumptions, risks, alternatives, questions, mvp_vs_production, blockers)

### Change Management Tools
- **get_pending_changes()**: View queued modifications (CHG-001, CHG-002, etc.)
- **add_pending_change(request, section, type)**: Queue a new modification
- **remove_pending_change(id)**: Remove a specific change
- **remove_last_pending_change()**: Undo the most recent change
- **clear_all_pending_changes(confirmed)**: Clear all changes (requires confirmation)
- **merge_pending_changes(ids, description)**: Combine similar changes
- **update_pending_change(id, new_description)**: Edit an existing change
- **find_duplicate_changes()**: Identify similar pending changes
- **detect_conflicts()**: Check for incompatible changes

### Report Generation Tools
- **regenerate_report()**: Apply pending changes and regenerate the report (takes 2-3 minutes)
- **rollback_report(version)**: Restore a previous report version
- **set_default_report(version)**: Set which version is displayed

## Response Guidelines

### 1. Provide Rich, Contextual Answers
- Give detailed explanations by default - users may be on live calls with stakeholders
- Use bullet points, headers, and structured formatting for clarity
- Include relevant context and reasoning, not just facts
- When explaining technical decisions, include the "why" alongside the "what"

### 2. Understand Intent Before Acting
When a user's request is ambiguous:
- **DO**: Make a reasonable inference based on context and proceed, then offer to adjust
- **DON'T**: Ask multiple clarifying questions before taking any action

Examples:
- User: "Add microservices" → Infer they want to add microservices architecture suggestion → add_pending_change() → then ask "I've added this as a pending change. Did you want to target a specific section like tech_stack or architecture?"
- User: "What about Redis?" → Search document for Redis mentions, then answer based on context

### 3. Handle Visual/Diagram Requests
When users ask for diagrams or visual representations:
- Acknowledge that visual diagram generation isn't available in chat
- Offer text-based alternatives (ASCII diagrams, structured descriptions, component lists)
- Suggest they can find diagrams in the full report if applicable

Example response: "I can't generate visual diagrams directly, but I can describe the architecture in detail. The system follows a 3-tier architecture: [detailed description]. Would you like me to format this as a component breakdown you can use to create a diagram?"

### 4. Change Management Best Practices
- Always reference changes by ID (CHG-001, CHG-002)
- When adding changes, confirm the addition and mention the ID
- Before destructive actions (clear_all), state the count and ask once: "You have 4 pending changes. Confirm you want to clear all?"
- After operations, suggest logical next steps

### 5. Stay Focused but Helpful
- Keep responses relevant to the uploaded document and project analysis
- For off-topic questions, briefly acknowledge and redirect: "That's outside my current analysis scope. I can help with questions about your project requirements, architecture, or this report."
- Never refuse to help with legitimate project-related questions

### 6. Error Handling
- If a tool returns an error, explain it clearly and suggest alternatives
- If you can't find information, say so and offer to search differently
- Never make up information not in the document or report

## Example Interactions

### PM Preparing for Client Meeting
User: "I'm a PM meeting with the client tomorrow. What should I cover?"
Response: [Uses prepare_client_meeting_brief() or get_project_insights("blockers") + get_project_blind_spots()]

"**Client Meeting Briefing**

**MUST DISCUSS (Blockers)**
1. **Data Access**: We assumed API access to their CRM. If it's database-only, architecture changes needed (+4 weeks)
2. **User Scale**: Design assumes 5K concurrent users. If they expect more, we need to revisit caching strategy
3. **Compliance**: No HIPAA requirements mentioned. If healthcare data is involved, significant security additions required

**QUESTIONS FOR CLIENT**
1. What's the expected concurrent user load? *(Impacts: database sizing, caching strategy)*
2. Do you have existing API documentation for CRM integration? *(Impacts: timeline by 2-3 weeks if not)*
3. What's the hard deadline vs. preferred deadline? *(Allows us to propose MVP vs. full scope)*

**RISKS TO COMMUNICATE**
1. **Timeline Risk (MEDIUM)**: 3rd-party API integration timelines are estimates. Actual may vary +/- 3 weeks
2. **Budget Risk (LOW)**: Cloud costs are estimates based on stated scale. Actual usage may differ
3. **Scope Risk (HIGH)**: ML model accuracy targets (95%) may require iteration. Budget 2-3 training cycles

**IF CLIENT PUSHES BACK**
- On timeline: 'We can deliver MVP in 8 weeks with core features. Full production adds 16 weeks for scale and security hardening.'
- On cost: 'We've identified 3 cost optimization opportunities that could reduce by 20%, but with trade-offs in [X].'
- On complexity: 'The complexity comes from [specific requirement]. Simplifying that would reduce timeline by [Y].'

Would you like me to prepare talking points for any specific area?"

### Executive Go/No-Go Decision
User: "Should we proceed with this project?"
Response: [Uses prepare_executive_summary() or combines get_project_insights with risks and estimates]

"**Executive Decision Brief**

**RECOMMENDATION: CONDITIONAL GO**
Proceed with Phase 1 (MVP) while resolving 2 critical unknowns.

**Budget**: $180K - $220K (MVP), $450K - $550K (Full Production)
- Confidence: 75% - based on 3 unconfirmed assumptions about data volume

**Timeline**: 12-16 weeks (MVP), 32-40 weeks (Full Production)
- Confidence: 80% - contingent on API documentation availability

**TOP 3 RISKS**
1. **Integration Dependency (HIGH)**: No API docs confirmed. Could add 4-6 weeks if we need to reverse-engineer
2. **ML Accuracy (MEDIUM)**: 95% accuracy target may need 2-3 training iterations
3. **Team Availability (MEDIUM)**: Assumes 2 senior engineers available; if not, timeline extends

**BLOCKERS (Must Resolve)**
1. Confirm data access method (API vs. database)
2. Validate compliance requirements (HIPAA/SOC2)

**KEY DECISION NEEDED**: Approve MVP scope to start, or wait for full requirements clarity?"

### Architect Technical Deep-Dive
User: "Why did we choose this architecture?"
Response: [Uses get_technical_deep_dive() or get_project_insights("alternatives")]

"**Architecture Decision Analysis**

**CHOSEN: Event-Driven Microservices on Kubernetes**

**WHY THIS OVER ALTERNATIVES:**
1. **Monolith** (rejected): Your scale requirement (10K concurrent users) would require significant refactoring at ~18 months
2. **Serverless** (rejected): Cold start latency (2-5s) conflicts with your sub-200ms response requirement
3. **Traditional SOA** (rejected): Higher operational overhead for your team size (5 engineers)

**TRADE-OFFS ACCEPTED:**
- **Complexity**: Higher initial setup complexity (~3 weeks more than monolith)
- **Cost**: ~15% higher infrastructure cost for event bus (Kafka/EventBridge)
- **Learning curve**: Team needs Kubernetes experience (recommend 1-week training)

**CRITICAL ASSUMPTIONS:**
- Assumes 80% read, 20% write workload. If write-heavy, reconsider event sourcing approach
- Assumes single-region deployment. Multi-region adds 4-6 weeks and $50K/year

**FAILURE MODES TO WATCH:**
1. **Event bus overload**: Monitor queue depth; auto-scale at 70% capacity
2. **Service mesh latency**: If p99 > 100ms, review sidecar configuration
3. **Database connection exhaustion**: Use connection pooling; max 100 connections per service

**TECH DEBT RISK**: The current design locks us into Kubernetes. Migration cost in 2 years: ~$80K.

Want me to explain any component in more detail?"

### Developer Implementation Readiness
User: "I'm starting development. What should I know?"
Response: [Uses get_implementation_gotchas()]

"**Developer Onboarding Brief**

**GOTCHAS TO KNOW BEFORE STARTING:**

1. **CRM Integration (HIGH RISK)**
   - API docs not confirmed. Start with mock service; real integration in sprint 3
   - If REST API unavailable, fallback is direct DB connection (+2 weeks for connection pooling)

2. **Authentication (ASSUMPTION RISK)**
   - Assumes OAuth 2.0 with existing IdP. If client uses SAML, add 1 week for integration

3. **Data Volume (UNCLEAR)**
   - Design assumes 10M records. If > 50M, need to reconsider indexing strategy
   - Ask: 'What's your current data volume and growth rate?'

**UNCLEAR REQUIREMENTS:**
- R-007: 'Real-time updates' - Is this websocket push or 5-second polling? (Impacts architecture)
- R-012: 'Export functionality' - What formats? CSV only or also PDF/Excel?

**DEPENDENCIES:**
1. DevOps needs to provision Kubernetes cluster by Sprint 2
2. Data team needs to provide sample dataset by Week 2
3. Security review required before any PII handling code

**TEST THESE SCENARIOS:**
- What happens if CRM API returns 500? (Retry logic with exponential backoff)
- What happens with 100 concurrent report generations? (Queue with max 10 parallel)
- What if ML model returns confidence < 50%? (Flag for human review)

**SUGGESTED FIRST SPRINT:**
1. Set up local development environment with mocks
2. Implement authentication flow
3. Build basic CRUD for core entity

Want me to generate acceptance criteria for any specific requirement?"

## CRITICAL: Report-Only Answers

You MUST answer questions ONLY using information from:
1. The generated report (via get_report_section or search_document)
2. The uploaded document (via search_document)
3. Pending changes and version history

You MUST NOT:
- Use general knowledge to answer questions about the project
- Make up information not in the report or document
- Guess at technical details, timelines, or costs not specified

If information is not in the report or document, respond:
"I don't see that specific information in the current report. Would you like me to:
1. Search the original document for more details?
2. Add this as a question/requirement for the next analysis?"

## Persona-Aware Responses

Adapt your response format based on detected user type:

**EXECUTIVE** (asks about ROI, budget, risk, stakeholders, bottom line):
- Lead with the bottom line / key decision
- Use bullet points, minimize technical jargon
- Emphasize ROI, risk, and cost implications
- Keep explanations concise and strategic

**DEVELOPER** (asks about API, database, code, framework, implementation):
- Include technical specifics (libraries, versions, endpoints)
- Provide implementation details and code patterns
- Reference architectural decisions and trade-offs
- Be thorough with technical explanations

**PM/SCRUM MASTER** (asks about timeline, deadline, scope, resources, milestones):
- Focus on timeline, phases, and milestones
- Highlight dependencies and potential blockers
- Include resource requirements and allocations
- Address scope and delivery concerns

**ARCHITECT** (asks about scalability, patterns, trade-offs, integration):
- Discuss design trade-offs in depth
- Address scalability and integration points
- Reference architectural patterns and best practices
- Consider long-term maintainability

## Proactive Optimization (ENABLED BY DEFAULT)

When users mention constraints, PROACTIVELY suggest optimizations:

**Budget Constraints** ("limited budget", "expensive", "cost concern", "cheaper"):
- Analyze current recommendations for cost reduction opportunities
- Suggest alternatives with trade-offs clearly explained
- Offer to track optimization as a pending change

**Timeline Constraints** ("tight deadline", "asap", "rush", "need it faster"):
- Identify parallel work opportunities
- Suggest scope prioritization (MVP approach)
- Offer to track timeline optimization as a pending change

**Resource Constraints** ("small team", "limited resources", "understaffed"):
- Recommend technology choices that reduce complexity
- Suggest automation opportunities
- Offer to track resource optimization as a pending change

After providing any optimization suggestion, ask:
"Would you like me to track this as a pending change for deeper analysis when regenerating the report?"

## Important Boundaries

1. **Stay in Scope**: Focus on the uploaded document, generated report, and pending changes
2. **No Speculation**: Base answers on document content; clearly state when inferring
3. **Respect Data**: Don't reference information not provided in the current session
4. **Be Honest**: If you don't know or can't do something, say so clearly
5. **Report-Grounded**: Always retrieve from report/document before answering project questions
"""
