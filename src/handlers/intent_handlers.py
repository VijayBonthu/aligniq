"""
Intent Handlers for Chat-with-Doc Conversations

Each handler is responsible for processing a specific type of user intent
and generating an appropriate response. This replaces the scattered
if/elif blocks in the original endpoint with clean, single-responsibility handlers.

Usage:
    handler = get_intent_handler(classification.primary_response_strategy)
    response = await handler.handle(classification, state, context, db)
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from datetime import datetime
from sqlalchemy.orm import Session

from utils.logger import logger
from utils.conversation_state import ConversationState, PendingActionState


class IntentHandler(ABC):
    """
    Abstract base class for all intent handlers.

    Each handler implements the handle() method to process a specific
    type of user intent and return a response dictionary.
    """

    @abstractmethod
    async def handle(
        self,
        classification: Dict[str, Any],
        state: ConversationState,
        context: Dict[str, Any],
        db: Session
    ) -> Dict[str, Any]:
        """
        Process the classified intent and generate a response.

        Args:
            classification: The semantic classification result
            state: Conversation state with pending actions
            context: Report context (summary, retrieved content, etc.)
            db: Database session

        Returns:
            Dict with:
            - message: The response text
            - action: Action type for logging
            - action_reason: Why this action was taken
            - [other metadata as needed]
        """
        pass


class ConfirmationHandler(IntentHandler):
    """
    Handles confirmation of pending actions.

    This handler:
    1. Validates that the pending action still exists
    2. Resolves the pending action as confirmed
    3. Tracks the change if it was a suggestion
    4. Handles conditional confirmations (e.g., "yes, but...")
    5. Processes any additional intents in the same message
    """

    async def handle(
        self,
        classification: Dict[str, Any],
        state: ConversationState,
        context: Dict[str, Any],
        db: Session
    ) -> Dict[str, Any]:
        from database_scripts import add_pending_change, get_pending_changes

        confirmation_map = classification.get("confirmation_map", {})
        intents = classification.get("intents", [])
        tracked_changes = []
        conditions = confirmation_map.get("conditions")

        # Process each confirmation
        for action_id, resolution in confirmation_map.items():
            if action_id == "conditions":
                continue  # Skip the conditions field

            if resolution in ["confirmed", "partial"]:
                pending_action = state.get_pending_action(action_id)

                if not pending_action:
                    logger.warning(f"Pending action {action_id} not found for confirmation")
                    continue

                # Resolve the pending action
                await state.resolve_pending_action(
                    action_id=action_id,
                    resolution="confirmed",
                    db=db,
                    resolution_message=conditions
                )

                # Handle different pending action types
                if pending_action.action_type == "suggestion":
                    # Track suggestion as a change
                    affected_sections = self._get_affected_sections(pending_action.category)
                    change_record = {
                        "type": pending_action.category or "modify_architecture",
                        "user_request": pending_action.content,
                        "affected_sections": affected_sections,
                        "timestamp": datetime.now().isoformat(),
                        "status": "pending",
                        "source": "suggestion_confirmed"
                    }

                    try:
                        chat_history_id = state.chat_history_id
                        add_result = await add_pending_change(
                            chat_history_id=chat_history_id,
                            change=change_record,
                            db=db
                        )

                        # Record transaction for undo capability
                        if add_result.get("status") == "success":
                            from database_scripts import record_transaction
                            await record_transaction(
                                chat_history_id=chat_history_id,
                                action_type="add_change",
                                action_data={
                                    "change_id": add_result.get("change_id"),
                                    "user_request": pending_action.content,
                                    "change_data": change_record
                                },
                                description=f"Added {add_result.get('change_id')}: {pending_action.content[:50]}...",
                                db=db
                            )

                        tracked_changes.append({
                            "change_id": add_result.get("change_id", "CHG-XXX"),
                            "content": pending_action.content,
                            "category": pending_action.category
                        })
                        logger.info(f"Tracked confirmed suggestion as {add_result.get('change_id')}")
                    except Exception as e:
                        logger.error(f"Failed to track confirmed suggestion: {str(e)}")

                elif pending_action.action_type in ["merge_duplicates", "execute_merge", "consolidate_all"]:
                    # Execute merge operation
                    result = await self._execute_merge(pending_action, state, db)
                    if result.get("status") == "success":
                        tracked_changes.append({
                            "change_id": result.get("new_change", {}).get("id", "CHG-XXX"),
                            "content": result.get("new_change", {}).get("user_request", "Merged change"),
                            "category": "merged",
                            "merged_from": result.get("removed_ids", [])
                        })

                elif pending_action.action_type == "remove_changes":
                    # Execute remove operation
                    result = await self._execute_remove(pending_action, state, db)
                    if result.get("status") == "success":
                        tracked_changes.append({
                            "change_id": "REMOVED",
                            "content": f"Removed {len(result.get('removed_ids', []))} change(s)",
                            "category": "removed"
                        })

                elif pending_action.action_type == "clear_all":
                    # Execute clear all operation
                    result = await self._execute_clear_all(pending_action, state, db)
                    if result.get("status") == "success":
                        tracked_changes.append({
                            "change_id": "ALL_CLEARED",
                            "content": f"Cleared {result.get('cleared_count', 0)} pending change(s)",
                            "category": "cleared"
                        })

        # Process any additional suggestions in the same message
        for intent in intents:
            if intent.get("type") == "explicit_suggestion":
                suggestion_content = intent.get("content", "")
                suggestion_action = intent.get("action", "modify_architecture")

                if suggestion_content:
                    affected_sections = self._get_affected_sections(suggestion_action)
                    change_record = {
                        "type": suggestion_action,
                        "user_request": suggestion_content,
                        "affected_sections": affected_sections,
                        "timestamp": datetime.now().isoformat(),
                        "status": "pending",
                        "source": "confirmation_with_new_suggestion"
                    }

                    try:
                        add_result = await add_pending_change(
                            chat_history_id=state.chat_history_id,
                            change=change_record,
                            db=db
                        )
                        tracked_changes.append({
                            "change_id": add_result.get("change_id", "CHG-XXX"),
                            "content": suggestion_content,
                            "category": suggestion_action
                        })
                    except Exception as e:
                        logger.error(f"Failed to track new suggestion: {str(e)}")

        # Generate response
        if tracked_changes:
            pending_count = len(await get_pending_changes(state.chat_history_id, db))
            response = self._generate_confirmation_response(tracked_changes, pending_count, conditions)
        else:
            # No changes were tracked - this means either:
            # 1. Classifier routed here incorrectly (should have been manage_pending_changes)
            # 2. Pending actions referenced in confirmation_map don't exist
            # 3. User confirmed but there was nothing to confirm
            #
            # Instead of keyword matching, we trust the classifier and provide a clear response
            # If this was meant to be a merge, the classifier should route to manage_pending_changes
            active_pending = state.get_active_pending_actions()
            if active_pending:
                # There are pending actions but we didn't process them - show them
                pending_list = state.format_pending_actions_summary()
                response = f"I have these pending actions awaiting your response:\n\n{pending_list}\n\nWould you like to confirm any of these?"
            else:
                # No pending actions at all
                response = "I don't have any pending suggestions awaiting your confirmation. What would you like to discuss or change?"

        return {
            "message": response,
            "action": "confirm_suggestion",
            "action_reason": f"Confirmed {len(tracked_changes)} change(s)",
            "tracked_changes": tracked_changes,
            "type": "suggestion_confirmed"
        }

    def _get_affected_sections(self, category: Optional[str]) -> List[str]:
        """Get sections affected by a change type."""
        section_map = {
            "modify_architecture": ["architecture", "components", "estimates", "executive_summary"],
            "modify_requirements": ["requirements", "architecture", "estimates"],
            "correct_assumptions": ["assumptions", "architecture", "executive_summary"]
        }
        return section_map.get(category, ["general"])

    def _generate_confirmation_response(
        self,
        tracked_changes: List[Dict],
        pending_count: int,
        conditions: Optional[str]
    ) -> str:
        """Generate a natural confirmation response."""
        # Check for special operations (merge/remove)
        if tracked_changes and tracked_changes[0].get("category") == "merged":
            change = tracked_changes[0]
            merged_from = change.get("merged_from", [])
            return f"Done! I've merged {len(merged_from)} changes into **{change['change_id']}**.\n\nYou now have {pending_count} pending modification{'s' if pending_count != 1 else ''}."

        if tracked_changes and tracked_changes[0].get("category") == "removed":
            return f"Done! {tracked_changes[0]['content']}\n\nYou now have {pending_count} pending modification{'s' if pending_count != 1 else ''}."

        if tracked_changes and tracked_changes[0].get("category") == "cleared":
            return f"Done! All pending changes have been cleared. You're starting fresh.\n\nFeel free to suggest new modifications to the report."

        if len(tracked_changes) == 1:
            change = tracked_changes[0]
            base_response = f"Got it. I've captured that as **{change['change_id']}** - {change['content']}."
        else:
            changes_list = "\n".join([
                f"- **{c['change_id']}** - {c['content']}"
                for c in tracked_changes
            ])
            base_response = f"Noted. I've captured {len(tracked_changes)} modifications:\n\n{changes_list}"

        # Add pending count info
        base_response += f"\n\nYou now have {pending_count} pending modification{'s' if pending_count > 1 else ''}."

        # Address conditions if any
        if conditions:
            base_response += f"\n\nRegarding your concern about {conditions} - I'll make sure to address that when regenerating the report."

        base_response += " When you're ready to incorporate these into the report, just say \"regenerate report\"."

        return base_response

    async def _execute_merge(
        self,
        pending_action: PendingActionState,
        state: ConversationState,
        db: Session
    ) -> Dict[str, Any]:
        """Execute a merge operation from a confirmed pending action."""
        from database_scripts import merge_pending_changes

        # Extract change IDs from context
        context = pending_action.context or ""
        change_ids = []

        # Parse context like "Duplicate changes: CHG-001, CHG-002" or "Merging: CHG-001, CHG-002"
        if ":" in context:
            ids_part = context.split(":")[-1].strip()
            # Extract CHG-XXX patterns
            import re
            change_ids = re.findall(r'CHG-\d+', ids_part)

        if not change_ids:
            logger.error(f"Could not extract change IDs from context: {context}")
            return {"status": "error", "message": "Could not determine which changes to merge"}

        # Get merged content from pending action content
        merged_content = pending_action.content
        if merged_content.startswith("Merge into: "):
            merged_content = merged_content[12:]
        elif merged_content.startswith("Consolidate"):
            # For consolidation, we need to generate merged content
            from database_scripts import get_pending_changes
            changes = await get_pending_changes(state.chat_history_id, db)
            changes_to_merge = [c for c in changes if c.get('id') in change_ids]
            if changes_to_merge:
                merged_content = max([c.get('user_request', '') for c in changes_to_merge], key=len)

        try:
            result = await merge_pending_changes(
                chat_history_id=state.chat_history_id,
                change_ids=change_ids,
                merged_content=merged_content,
                db=db
            )
            logger.info(f"Executed merge: {result}")
            return result
        except Exception as e:
            logger.error(f"Error executing merge: {str(e)}")
            return {"status": "error", "message": str(e)}

    async def _execute_remove(
        self,
        pending_action: PendingActionState,
        state: ConversationState,
        db: Session
    ) -> Dict[str, Any]:
        """Execute a remove operation from a confirmed pending action."""
        from database_scripts import remove_pending_change

        # Extract change IDs from context
        context = pending_action.context or ""
        change_ids = []

        # Parse context or content like "Remove changes: CHG-001, CHG-002"
        import re
        change_ids = re.findall(r'CHG-\d+', pending_action.content + " " + context)

        if not change_ids:
            logger.error(f"Could not extract change IDs from: {pending_action.content}")
            return {"status": "error", "message": "Could not determine which changes to remove"}

        removed_ids = []
        for change_id in change_ids:
            try:
                result = await remove_pending_change(
                    chat_history_id=state.chat_history_id,
                    change_id=change_id,
                    db=db
                )
                if result.get("status") == "success":
                    removed_ids.append(change_id)
            except Exception as e:
                logger.error(f"Error removing change {change_id}: {str(e)}")

        if removed_ids:
            logger.info(f"Removed changes: {removed_ids}")
            return {"status": "success", "removed_ids": removed_ids}
        else:
            return {"status": "error", "message": "Failed to remove changes"}

    async def _execute_clear_all(
        self,
        pending_action: PendingActionState,
        state: ConversationState,
        db: Session
    ) -> Dict[str, Any]:
        """Execute a clear all operation from a confirmed pending action."""
        from database_scripts import clear_pending_changes, record_transaction, get_pending_changes

        try:
            # Get current changes for transaction recording (enables undo)
            current_changes = await get_pending_changes(state.chat_history_id, db)
            cleared_count = len(current_changes)

            if cleared_count == 0:
                return {"status": "success", "cleared_count": 0}

            # Record transaction for undo capability
            await record_transaction(
                chat_history_id=state.chat_history_id,
                action_type="clear_all",
                action_data={
                    "cleared_changes": current_changes,
                    "cleared_count": cleared_count
                },
                description=f"Cleared {cleared_count} pending change(s)",
                db=db
            )

            # Execute clear
            result = await clear_pending_changes(state.chat_history_id, db)

            if result.get("status") == "success":
                logger.info(f"Cleared {cleared_count} pending changes for {state.chat_history_id}")
                return {
                    "status": "success",
                    "cleared_count": cleared_count
                }
            else:
                return {"status": "error", "message": "Failed to clear changes"}

        except Exception as e:
            logger.error(f"Error executing clear all: {str(e)}")
            return {"status": "error", "message": str(e)}


class DeclineHandler(IntentHandler):
    """Handles declining of pending actions."""

    async def handle(
        self,
        classification: Dict[str, Any],
        state: ConversationState,
        context: Dict[str, Any],
        db: Session
    ) -> Dict[str, Any]:
        confirmation_map = classification.get("confirmation_map", {})

        # Resolve declined actions
        for action_id, resolution in confirmation_map.items():
            if action_id == "conditions":
                continue
            if resolution == "declined":
                await state.resolve_pending_action(
                    action_id=action_id,
                    resolution="declined",
                    db=db
                )

        return {
            "message": "Understood, we'll leave that as is. What else would you like to discuss about the architecture?",
            "action": "decline_suggestion",
            "action_reason": "User declined pending suggestion",
            "type": "suggestion_declined"
        }


class ArchitectureChallengeHandler(IntentHandler):
    """
    Handles challenges to architecture decisions.

    This handler:
    1. Extracts the defense topic from the classification
    2. Retrieves relevant architecture context from the report
    3. Generates a defense response that explains the reasoning
    4. Offers to track the suggestion if it has merit
    """

    async def handle(
        self,
        classification: Dict[str, Any],
        state: ConversationState,
        context: Dict[str, Any],
        db: Session
    ) -> Dict[str, Any]:
        from utils.router_llm import generate_architecture_defense

        defense_topic = classification.get("defense_topic", "the architecture decision")
        user_message = classification.get("user_message", "")

        # Extract architecture context from report summary
        report_summary = context.get("report_summary", {})
        architecture_context = self._extract_architecture_context(report_summary, defense_topic)
        trade_offs = self._extract_trade_offs(report_summary, defense_topic)
        recent_messages = context.get("recent_messages", [])

        try:
            # Generate defense response
            response = await generate_architecture_defense(
                report_summary=report_summary,
                challenge_topic=defense_topic,
                user_message=user_message,
                architecture_context=architecture_context,
                trade_offs=trade_offs,
                recent_messages=recent_messages
            )

            # Check if there's an explicit suggestion to track
            explicit_suggestions = [
                i for i in classification.get("intents", [])
                if i.get("type") == "explicit_suggestion"
            ]

            # ALWAYS create a pending action when defending architecture
            # because the defense response offers to track the user's alternative
            # This ensures "yes" can be properly mapped to a confirmation
            suggestion_content = None
            if explicit_suggestions:
                suggestion_content = explicit_suggestions[0].get("content", "")
            else:
                # Extract implied suggestion from the challenge
                # e.g., "Why 2 DBs?" implies "use single DB"
                suggestion_content = self._extract_implied_suggestion(user_message, defense_topic)

            if suggestion_content:
                action_id = await state.add_pending_action(
                    action_type="suggestion",
                    content=suggestion_content,
                    db=db,
                    context=f"User challenged: {defense_topic}",
                    category="modify_architecture"
                )
                logger.info(f"Created pending action {action_id} for architecture challenge: {suggestion_content}")

                # Return with pending suggestion for the response
                return {
                    "message": response,
                    "action": "architecture_defended",
                    "action_reason": f"Defended: {defense_topic}",
                    "type": "architecture_defense",
                    "pending_suggestion": {
                        "action_id": action_id,
                        "content": suggestion_content,
                        "category": "modify_architecture",
                        "awaiting_confirmation": True
                    }
                }

            return {
                "message": response,
                "action": "architecture_defended",
                "action_reason": f"Defended: {defense_topic}",
                "type": "architecture_defense"
            }

        except Exception as e:
            logger.error(f"Error generating architecture defense: {str(e)}")
            return {
                "message": "That's a fair question. Let me explain the reasoning behind that decision and we can discuss alternatives if you'd like.",
                "action": "architecture_defended",
                "action_reason": f"Defense failed, generic response: {str(e)}",
                "type": "architecture_defense"
            }

    def _extract_architecture_context(self, report_summary: Dict, topic: str) -> str:
        """Extract relevant architecture context from report summary."""
        # Try to find architecture-related content
        if isinstance(report_summary, dict):
            arch_content = report_summary.get("architecture", "")
            components = report_summary.get("components", "")
            tech_stack = report_summary.get("tech_stack", "")
            return f"Architecture: {arch_content}\nComponents: {components}\nTech Stack: {tech_stack}"
        return str(report_summary)[:2000]

    def _extract_trade_offs(self, report_summary: Dict, topic: str) -> str:
        """Extract trade-offs from report summary."""
        if isinstance(report_summary, dict):
            trade_offs = report_summary.get("trade_offs", "")
            considerations = report_summary.get("considerations", "")
            return f"Trade-offs: {trade_offs}\nConsiderations: {considerations}"
        return "Trade-offs were considered during design."

    def _extract_implied_suggestion(self, user_message: str, defense_topic: str) -> str:
        """
        Extract the implied suggestion from an architecture challenge.

        When user says "Why 2 DBs instead of 1?" they're implying "use single DB".
        When user says "Isn't DynamoDB expensive?" they're implying "use cheaper alternative".

        Args:
            user_message: The user's challenge message
            defense_topic: The topic being defended

        Returns:
            The implied suggestion as a trackable change request
        """
        msg_lower = user_message.lower()

        # Common patterns and their implied suggestions
        if "why" in msg_lower and ("two" in msg_lower or "2" in msg_lower or "multiple" in msg_lower):
            # "Why 2 DBs?" -> "Consolidate to single database"
            return f"Consolidate architecture: {defense_topic}"

        if "expensive" in msg_lower or "cost" in msg_lower:
            # "Isn't X expensive?" -> "Consider cost-effective alternative"
            return f"Evaluate cost-effective alternatives for: {defense_topic}"

        if "complex" in msg_lower or "complicated" in msg_lower or "overcomplicated" in msg_lower:
            # "This is overcomplicated" -> "Simplify architecture"
            return f"Simplify architecture approach for: {defense_topic}"

        if "instead" in msg_lower or "why not" in msg_lower:
            # "Why not use X instead?" -> extract X
            return f"Consider alternative approach: {defense_topic}"

        if "necessary" in msg_lower or "need" in msg_lower:
            # "Is X really necessary?" -> "Evaluate if X is required"
            return f"Evaluate necessity of: {defense_topic}"

        # Default: use the defense topic as the suggestion base
        return f"Consider alternative approach for: {defense_topic}"
        return "Trade-offs were considered during architecture design."


class QuestionHandler(IntentHandler):
    """
    Handles questions about the report.

    Uses vector retrieval to find relevant context and generates
    an informed response.
    """

    async def handle(
        self,
        classification: Dict[str, Any],
        state: ConversationState,
        context: Dict[str, Any],
        db: Session
    ) -> Dict[str, Any]:
        from utils.router_llm import generate_action_response
        from vectordb.vector_db import retrieve_similar_embeddings
        from config import settings

        question_intents = [
            i for i in classification.get("intents", [])
            if i.get("type") == "question"
        ]

        user_message = classification.get("user_message", "")
        question_content = question_intents[0].get("content", user_message) if question_intents else user_message

        # Retrieve relevant context
        retrieved_context = "N/A"
        try:
            vector_results = await retrieve_similar_embeddings(
                query_text=question_content,
                model=settings.EMBEDDING_MODEL,
                chat_history_id=state.chat_history_id,
                top_k=3
            )
            if vector_results and "documents" in vector_results and vector_results["documents"]:
                retrieved_context = "\n\n".join(vector_results["documents"][0])
        except Exception as e:
            logger.warning(f"Vector retrieval failed: {str(e)}")

        # Generate response
        try:
            report_summary = context.get("report_summary", {})
            conversation_context = context.get("recent_messages", [])

            response = await generate_action_response(
                report_summary=report_summary,
                conversation_context=conversation_context,
                user_message=user_message,
                action="answer_question_from_report",
                action_reason="User asked a question",
                retrieved_context=retrieved_context
            )

            return {
                "message": response,
                "action": "question_answered",
                "action_reason": "Answered user question",
                "type": "question_response"
            }

        except Exception as e:
            logger.error(f"Error generating question response: {str(e)}")
            return {
                "message": "I apologize, I encountered an issue retrieving that information. Could you rephrase your question?",
                "action": "question_answered",
                "action_reason": f"Error: {str(e)}",
                "type": "question_response"
            }


class SuggestionHandler(IntentHandler):
    """
    Handles explicit and implicit suggestions.

    - Explicit suggestions are auto-tracked
    - Implicit suggestions are offered for confirmation
    """

    async def handle(
        self,
        classification: Dict[str, Any],
        state: ConversationState,
        context: Dict[str, Any],
        db: Session
    ) -> Dict[str, Any]:
        from database_scripts import add_pending_change, get_pending_changes
        from utils.router_llm import generate_hybrid_response

        intents = classification.get("intents", [])
        explicit_suggestions = [i for i in intents if i.get("type") == "explicit_suggestion"]
        implicit_suggestions = [i for i in intents if i.get("type") == "implicit_suggestion"]

        tracked_changes = []

        # Auto-track explicit suggestions
        for suggestion in explicit_suggestions:
            suggestion_content = suggestion.get("content", "")
            suggestion_action = suggestion.get("action", "modify_architecture")

            if suggestion_content:
                affected_sections = self._get_affected_sections(suggestion_action)
                change_record = {
                    "type": suggestion_action,
                    "user_request": suggestion_content,
                    "affected_sections": affected_sections,
                    "timestamp": datetime.now().isoformat(),
                    "status": "pending",
                    "source": "explicit_suggestion"
                }

                try:
                    add_result = await add_pending_change(
                        chat_history_id=state.chat_history_id,
                        change=change_record,
                        db=db
                    )

                    # Record transaction for undo capability
                    if add_result.get("status") == "success":
                        from database_scripts import record_transaction
                        await record_transaction(
                            chat_history_id=state.chat_history_id,
                            action_type="add_change",
                            action_data={
                                "change_id": add_result.get("change_id"),
                                "user_request": suggestion_content,
                                "change_data": change_record
                            },
                            description=f"Added {add_result.get('change_id')}: {suggestion_content[:50]}...",
                            db=db
                        )

                    tracked_changes.append({
                        "change_id": add_result.get("change_id", "CHG-XXX"),
                        "content": suggestion_content,
                        "category": suggestion_action
                    })
                except Exception as e:
                    logger.error(f"Failed to track suggestion: {str(e)}")

        # Offer implicit suggestions for confirmation
        pending_suggestion = None
        if implicit_suggestions:
            first_implicit = implicit_suggestions[0]
            action_id = await state.add_pending_action(
                action_type="suggestion",
                content=first_implicit.get("content", ""),
                db=db,
                context="Implicit suggestion from user message",
                category=first_implicit.get("action", "modify_architecture")
            )
            pending_suggestion = {
                "action_id": action_id,
                "content": first_implicit.get("content", ""),
                "category": first_implicit.get("action", "modify_architecture"),
                "awaiting_confirmation": True
            }

        # Generate response
        report_summary = context.get("report_summary", {})
        user_message = classification.get("user_message", "")

        try:
            response = await generate_hybrid_response(
                report_summary=report_summary,
                hybrid_context={"recent_messages": context.get("recent_messages", [])},
                user_message=user_message,
                intent=classification,
                retrieved_context="N/A"
            )

            # Add tracking confirmation to response
            if tracked_changes:
                pending_count = len(await get_pending_changes(state.chat_history_id, db))
                if len(tracked_changes) == 1:
                    change = tracked_changes[0]
                    response += f"\n\nI've captured that as **{change['change_id']}** ({pending_count} pending total)."
                else:
                    changes_list = ", ".join([f"**{c['change_id']}**" for c in tracked_changes])
                    response += f"\n\nI've captured those as {changes_list} ({pending_count} pending total)."

            return {
                "message": response,
                "action": "suggestions_processed",
                "action_reason": f"Tracked {len(tracked_changes)} explicit, {len(implicit_suggestions)} pending",
                "tracked_changes": tracked_changes,
                "pending_suggestion": pending_suggestion,
                "type": "suggestion_response"
            }

        except Exception as e:
            logger.error(f"Error generating suggestion response: {str(e)}")
            raise

    def _get_affected_sections(self, category: Optional[str]) -> List[str]:
        """Get sections affected by a change type."""
        section_map = {
            "modify_architecture": ["architecture", "components", "estimates", "executive_summary"],
            "modify_requirements": ["requirements", "architecture", "estimates"],
            "correct_assumptions": ["assumptions", "architecture", "executive_summary"]
        }
        return section_map.get(category, ["general"])


class CommandHandler(IntentHandler):
    """
    Handles system commands like regenerate, undo, show history, etc.

    Routes to appropriate command-specific logic based on the action type.
    """

    async def handle(
        self,
        classification: Dict[str, Any],
        state: ConversationState,
        context: Dict[str, Any],
        db: Session
    ) -> Dict[str, Any]:
        intents = classification.get("intents", [])
        command_intents = [i for i in intents if i.get("type") == "command"]

        if not command_intents:
            return {
                "message": "I'm not sure what command you're trying to run. Try 'show pending changes' or 'regenerate report'.",
                "action": "command_unclear",
                "action_reason": "No command intent found"
            }

        action = command_intents[0].get("action", "general_discussion")

        # Route to specific command handlers
        # These would typically call existing functions from services.py or database_scripts.py
        command_handlers = {
            "regenerate_full_report": self._handle_regenerate,
            "show_pending_changes": self._handle_show_pending,
            "show_version_history": self._handle_show_history,
            "undo_last_change": self._handle_undo_last,
            "undo_specific_change": self._handle_undo_specific,
            "clear_all_changes": self._handle_clear_all,
            "rollback_to_version": self._handle_rollback,
            "export_report": self._handle_export,
            "switch_report_version": self._handle_switch_report_version
        }

        handler = command_handlers.get(action, self._handle_unknown_command)
        return await handler(classification, state, context, db)

    async def _handle_regenerate(self, classification, state, context, db) -> Dict[str, Any]:
        """
        Handle full report regeneration with pending changes as constraints.

        Flow:
        1. Get pending changes (quick check)
        2. Check for conflicts
        3. Get full regeneration context (document, presales data, pending changes)
        4. Run full 9-agent pipeline with constraints + presales context
        5. Generate report summary
        6. Create new report version
        7. Update vector DB
        8. Clear pending changes
        9. Return success response with report
        """
        from database_scripts import (
            get_pending_changes,
            detect_conflicts,
            get_regeneration_context,
            create_new_report_version,
            clear_pending_changes
        )
        from agents.agentic_workflow import run_pipeline_with_constraints, main_report_summary
        from utils.router_llm import generate_conflict_resolution
        from vectordb.chunking import chunk_text
        from vectordb.vector_db import create_embeddings
        from config import settings

        chat_history_id = state.chat_history_id
        user_id = context.get("user_id")

        if not user_id:
            return {
                "message": "Unable to identify user. Please try again.",
                "action": "regenerate_error",
                "action_reason": "Missing user_id"
            }

        # Step 1: Get pending changes (quick check)
        try:
            pending_changes = await get_pending_changes(chat_history_id, db)
        except Exception as e:
            logger.error(f"Failed to get pending changes: {str(e)}")
            return {
                "message": "I couldn't retrieve the pending changes. Please try again.",
                "action": "regenerate_error",
                "action_reason": str(e)
            }

        if not pending_changes:
            return {
                "message": "There are no pending changes to apply. Your report is up to date.\n\nYou can suggest modifications like:\n- \"Use PostgreSQL instead of MongoDB\"\n- \"Add real-time notifications feature\"\n- \"Consider microservices architecture\"\n\nI'll track them as pending changes, and you can regenerate the report when ready.",
                "action": "regenerate_no_changes",
                "action_reason": "No pending changes found"
            }

        # Step 2: Check for conflicts
        conflicts = detect_conflicts(pending_changes)
        if conflicts:
            try:
                conflict_msg = await generate_conflict_resolution(conflicts, pending_changes)
                return {
                    "message": conflict_msg,
                    "action": "regenerate_conflict",
                    "action_reason": f"Found {len(conflicts)} conflict(s)",
                    "conflicts": conflicts
                }
            except Exception as e:
                logger.error(f"Failed to generate conflict resolution: {str(e)}")
                # Fallback to simple conflict message
                conflict_list = "\n".join([
                    f"- {c.get('description', 'Unknown conflict')}"
                    for c in conflicts
                ])
                return {
                    "message": f"I found {len(conflicts)} conflict(s) in your pending changes:\n\n{conflict_list}\n\nPlease resolve these before regenerating. You can use 'undo CHG-XXX' to remove a conflicting change.",
                    "action": "regenerate_conflict",
                    "action_reason": f"Found {len(conflicts)} conflicts",
                    "conflicts": conflicts
                }

        # Step 3: Get full regeneration context
        try:
            regen_context = await get_regeneration_context(chat_history_id, user_id, db)
        except Exception as e:
            logger.error(f"Failed to get regeneration context: {str(e)}")
            return {
                "message": "I couldn't retrieve the necessary context for regeneration. Please try again.",
                "action": "regenerate_error",
                "action_reason": str(e)
            }

        # Step 4: Run FULL 9-agent pipeline with constraints + presales context
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
            processing_time = result.get("processing_time", 0)
            logger.info(f"Full pipeline completed in {processing_time:.2f}s with {len(pending_changes)} constraints")

        except Exception as e:
            logger.error(f"Report generation failed: {str(e)}")
            return {
                "message": f"Report generation encountered an error: {str(e)}\n\nPlease try again. If the problem persists, try removing some pending changes and regenerating.",
                "action": "regenerate_error",
                "action_reason": str(e)
            }

        # Step 5: Generate report summary
        try:
            new_version_number = regen_context.get("current_version", 0) + 1
            summary_report = await main_report_summary(regenerated_report, new_version_number)
        except Exception as e:
            logger.error(f"Failed to generate report summary: {str(e)}")
            # Use empty summary as fallback
            summary_report = {"version": f"v{new_version_number}", "error": "Summary generation failed"}

        # Step 6: Create new report version
        try:
            version_result = await create_new_report_version(
                chat_history_id=chat_history_id,
                user_id=user_id,
                report_content=regenerated_report,
                summary_report=summary_report,
                changes_applied=pending_changes,
                db=db
            )
            new_version = version_result.get("version_number", new_version_number)
        except Exception as e:
            logger.error(f"Failed to create new report version: {str(e)}")
            return {
                "message": f"Report was generated but couldn't be saved: {str(e)}\n\nPlease try again.",
                "action": "regenerate_error",
                "action_reason": str(e),
                "report_content": regenerated_report  # Include report even if save failed
            }

        # Step 7: Update vector DB with new report content
        try:
            report_chunks = await chunk_text(regenerated_report, chunk_size=1000, chunk_overlap=200)
            await create_embeddings(
                texts=report_chunks,
                model=settings.EMBEDDING_MODEL,
                chat_history_id=chat_history_id
            )
            logger.info(f"Updated vector DB with {len(report_chunks)} chunks for chat_history_id: {chat_history_id}")
        except Exception as e:
            logger.warning(f"Failed to update vector DB (non-fatal): {str(e)}")
            # This is non-fatal - the report is still saved

        # Step 8: Clear pending changes (they've been applied)
        try:
            await clear_pending_changes(chat_history_id, db)
            logger.info(f"Cleared {len(pending_changes)} pending changes after regeneration")
        except Exception as e:
            logger.warning(f"Failed to clear pending changes (non-fatal): {str(e)}")
            # This is non-fatal - changes are applied in new version anyway

        # Step 9: Build success response
        changes_summary = "\n".join([
            f"- {c.get('id', 'CHG-?')}: {c.get('user_request', '')[:60]}..."
            for c in pending_changes[:5]  # Show first 5
        ])
        if len(pending_changes) > 5:
            changes_summary += f"\n- ... and {len(pending_changes) - 5} more"

        return {
            "message": f"**Report Regenerated Successfully** (Version {new_version})\n\nApplied {len(pending_changes)} change(s):\n{changes_summary}\n\nThe report has been updated with all your requested modifications. You can view the full report or ask me any questions about it.",
            "action": "regenerate_full_report",
            "action_reason": f"Applied {len(pending_changes)} constraints",
            "report_content": regenerated_report,
            "version_number": new_version,
            "changes_applied": len(pending_changes),
            "processing_time": processing_time,
            "type": "report_regeneration"
        }

    async def _handle_show_pending(self, classification, state, context, db) -> Dict[str, Any]:
        """Handle show pending changes command."""
        from database_scripts import get_pending_changes

        changes = await get_pending_changes(state.chat_history_id, db)

        if not changes:
            return {
                "message": "You have no pending changes. Feel free to suggest modifications and they'll be tracked here.",
                "action": "show_pending_changes",
                "action_reason": "No pending changes",
                "pending_changes": []
            }

        changes_list = "\n".join([
            f"- **{c.get('id', 'CHG-?')}**: {c.get('user_request', '')[:80]}..."
            for c in changes
        ])

        return {
            "message": f"You have {len(changes)} pending change(s):\n\n{changes_list}\n\nSay 'regenerate report' to apply these, or 'undo CHG-XXX' to remove one.",
            "action": "show_pending_changes",
            "action_reason": f"Showing {len(changes)} pending changes",
            "pending_changes": changes
        }

    async def _handle_show_history(self, classification, state, context, db) -> Dict[str, Any]:
        """Handle show version history command."""
        return {
            "message": "Let me fetch the version history for this report...",
            "action": "show_version_history",
            "action_reason": "User requested version history",
            "requires_history_fetch": True
        }

    async def _handle_undo_last(self, classification, state, context, db) -> Dict[str, Any]:
        """Handle undo last change command - EXECUTES the undo."""
        from database_scripts import (
            get_pending_changes,
            remove_last_pending_change,
            record_transaction
        )

        chat_history_id = state.chat_history_id

        # Get current changes
        pending = await get_pending_changes(chat_history_id, db)

        if not pending:
            return {
                "message": "There's nothing to undo. You haven't added any changes yet.\n\nSay 'show pending changes' to see your current modifications.",
                "action": "undo_nothing",
                "action_reason": "No pending changes"
            }

        # Remove and get the last change
        result = await remove_last_pending_change(chat_history_id, db)

        if result.get("status") == "success":
            removed = result.get("removed_change", {})
            remaining = result.get("remaining_count", 0)

            # Record transaction for redo capability
            await record_transaction(
                chat_history_id=chat_history_id,
                action_type="remove_change",
                action_data={"change_data": removed},
                description=f"Undid {removed.get('id', 'last change')}",
                db=db
            )

            return {
                "message": f"Done! I've undone **{removed.get('id', 'the last change')}**: \"{removed.get('user_request', '')[:60]}...\"\n\nYou now have {remaining} pending change(s).",
                "action": "undo_success",
                "action_reason": f"Removed {removed.get('id')}",
                "undone_change": removed
            }

        if result.get("status") == "no_changes":
            return {
                "message": "There's nothing to undo. You haven't added any changes yet.",
                "action": "undo_nothing",
                "action_reason": "No pending changes"
            }

        return {
            "message": "I couldn't undo that change. Please try again.",
            "action": "undo_error",
            "action_reason": result.get("message", "Unknown error")
        }

    async def _handle_undo_specific(self, classification, state, context, db) -> Dict[str, Any]:
        """Handle undo specific change command - EXECUTES the undo."""
        from database_scripts import (
            get_pending_changes,
            remove_pending_change,
            record_transaction
        )
        import re

        chat_history_id = state.chat_history_id
        user_message = classification.get("user_message", "")

        # Extract change ID from classification or message
        change_ids = []
        for intent in classification.get("intents", []):
            if intent.get("change_ids"):
                change_ids.extend(intent.get("change_ids"))

        # Also try regex extraction from user message
        found_ids = re.findall(r'CHG-\d+', user_message.upper())
        change_ids.extend(found_ids)
        change_ids = list(set(change_ids))

        if not change_ids:
            return {
                "message": "Please specify which change to undo, e.g., 'undo CHG-001'.\n\nSay 'show pending changes' to see your current changes.",
                "action": "undo_specify",
                "action_reason": "No change ID specified"
            }

        target_id = change_ids[0]

        # Get current changes to find the one being removed
        pending = await get_pending_changes(chat_history_id, db)
        target_change = next((c for c in pending if c.get("id") == target_id), None)

        if not target_change:
            return {
                "message": f"I couldn't find **{target_id}** in your pending changes.\n\nSay 'show pending changes' to see what's available.",
                "action": "undo_not_found",
                "action_reason": f"{target_id} not found"
            }

        # Execute removal
        result = await remove_pending_change(chat_history_id, target_id, db)

        if result.get("status") == "success":
            remaining = result.get("remaining_count", 0)

            # Record transaction for redo capability
            await record_transaction(
                chat_history_id=chat_history_id,
                action_type="remove_change",
                action_data={"change_data": target_change},
                description=f"Removed {target_id}",
                db=db
            )

            return {
                "message": f"Done! I've removed **{target_id}**: \"{target_change.get('user_request', '')[:60]}...\"\n\nYou now have {remaining} pending change(s).",
                "action": "undo_success",
                "action_reason": f"Removed {target_id}",
                "undone_change": target_change
            }

        return {
            "message": f"I couldn't remove {target_id}. Please try again.",
            "action": "undo_error",
            "action_reason": result.get("message", "Unknown error")
        }

    async def _handle_clear_all(self, classification, state, context, db) -> Dict[str, Any]:
        """Handle clear all changes command - requires confirmation."""
        # Add a pending action for confirmation
        action_id = await state.add_pending_action(
            action_type="clear_all",
            content="Clear all pending changes",
            db=db,
            context="User requested to clear all changes"
        )

        return {
            "message": f"Are you sure you want to clear all pending changes? This cannot be undone. Reply 'yes' to confirm or 'no' to cancel.",
            "action": "clear_all_confirmation",
            "action_reason": "Awaiting confirmation for clear all",
            "pending_action_id": action_id
        }

    async def _handle_rollback(self, classification, state, context, db) -> Dict[str, Any]:
        """Handle rollback to version command - requires confirmation."""
        return {
            "message": "Rolling back to a previous version will discard current changes. Please confirm this action.",
            "action": "rollback_confirmation",
            "action_reason": "Awaiting confirmation for rollback",
            "requires_confirmation": True
        }

    async def _handle_export(self, classification, state, context, db) -> Dict[str, Any]:
        """Handle export report command."""
        return {
            "message": "I'll prepare the report for export...",
            "action": "export_report",
            "action_reason": "User requested export",
            "requires_export": True
        }

    async def _handle_switch_report_version(self, classification, state, context, db) -> Dict[str, Any]:
        """
        Handle switch/set report version command.

        Switches the current/default report version to a specified version number.
        """
        from database_scripts import set_default_version

        # Extract version number from classification
        version_number = self._extract_version_number(classification)

        if version_number is None:
            return {
                "message": "Which version would you like to switch to? Please specify a version number (e.g., 'switch to version 2').",
                "action": "switch_report_version_prompt",
                "action_reason": "Version number not specified"
            }

        # Get user_id from context
        user_id = context.get("user_id")
        if not user_id:
            logger.error("user_id not found in context for switch_report_version")
            return {
                "message": "I couldn't complete this action. Please try again.",
                "action": "switch_report_version_error",
                "action_reason": "user_id not in context"
            }

        try:
            result = await set_default_version(
                chat_history_id=context["chat_history_id"],
                user_id=user_id,
                version_number=version_number,
                db=db
            )

            if result.get("status") == "success":
                return {
                    "message": f"Done! Version {version_number} is now your current report. Any questions or changes will reference this version.",
                    "action": "switch_report_version",
                    "action_reason": f"Switched to version {version_number}",
                    "switched_to_version": version_number
                }
            else:
                error_msg = result.get("message", "Unknown error")
                return {
                    "message": f"I couldn't switch to version {version_number}. {error_msg}",
                    "action": "switch_report_version_error",
                    "action_reason": error_msg
                }
        except Exception as e:
            logger.error(f"Error switching report version: {str(e)}")
            return {
                "message": f"I encountered an error while switching versions. Please try again.",
                "action": "switch_report_version_error",
                "action_reason": str(e)
            }

    def _extract_version_number(self, classification: Dict[str, Any]) -> Optional[int]:
        """
        Extract version number from classification or user message.

        Checks:
        1. version_number field in intents
        2. Parses "version X" pattern from user message
        """
        import re

        # Check intents for version_number field
        for intent in classification.get("intents", []):
            version = intent.get("version_number")
            if version is not None:
                try:
                    return int(version)
                except (ValueError, TypeError):
                    pass

        # Parse from user message
        user_message = classification.get("user_message", "")

        # Match patterns like "version 2", "v2", "version2"
        patterns = [
            r'version\s*(\d+)',
            r'\bv(\d+)\b',
            r'to\s+(\d+)\s*$'  # "switch to 2"
        ]

        for pattern in patterns:
            match = re.search(pattern, user_message, re.IGNORECASE)
            if match:
                return int(match.group(1))

        return None

    async def _handle_unknown_command(self, classification, state, context, db) -> Dict[str, Any]:
        """Handle unknown command."""
        return {
            "message": "I'm not sure what you'd like me to do. Available commands: 'regenerate report', 'show pending changes', 'undo last change', 'show version history', 'switch to version X'.",
            "action": "unknown_command",
            "action_reason": "Command not recognized"
        }


class HybridQueryHandler(IntentHandler):
    """
    Handles hybrid queries (question + suggestion).

    Answers the question first, then processes suggestions.
    """

    async def handle(
        self,
        classification: Dict[str, Any],
        state: ConversationState,
        context: Dict[str, Any],
        db: Session
    ) -> Dict[str, Any]:
        from utils.router_llm import generate_hybrid_response
        from vectordb.vector_db import retrieve_similar_embeddings
        from config import settings

        intents = classification.get("intents", [])
        question_intents = [i for i in intents if i.get("type") == "question"]
        explicit_suggestions = [i for i in intents if i.get("type") == "explicit_suggestion"]
        implicit_suggestions = [i for i in intents if i.get("type") == "implicit_suggestion"]

        user_message = classification.get("user_message", "")

        # Retrieve context for question
        retrieved_context = "N/A"
        if question_intents:
            question_content = question_intents[0].get("content", user_message)
            try:
                vector_results = await retrieve_similar_embeddings(
                    query_text=question_content,
                    model=settings.EMBEDDING_MODEL,
                    chat_history_id=state.chat_history_id,
                    top_k=3
                )
                if vector_results and "documents" in vector_results and vector_results["documents"]:
                    retrieved_context = "\n\n".join(vector_results["documents"][0])
            except Exception as e:
                logger.warning(f"Vector retrieval failed: {str(e)}")

        # Generate hybrid response
        report_summary = context.get("report_summary", {})

        response = await generate_hybrid_response(
            report_summary=report_summary,
            hybrid_context={"recent_messages": context.get("recent_messages", [])},
            user_message=user_message,
            intent=classification,
            retrieved_context=retrieved_context
        )

        # Process suggestions (similar to SuggestionHandler)
        tracked_changes = []
        pending_suggestion = None

        # Track explicit suggestions
        for suggestion in explicit_suggestions:
            from database_scripts import add_pending_change

            suggestion_content = suggestion.get("content", "")
            suggestion_action = suggestion.get("action", "modify_architecture")

            if suggestion_content:
                change_record = {
                    "type": suggestion_action,
                    "user_request": suggestion_content,
                    "affected_sections": ["architecture"],
                    "timestamp": datetime.now().isoformat(),
                    "status": "pending",
                    "source": "hybrid_explicit_suggestion"
                }

                try:
                    add_result = await add_pending_change(
                        chat_history_id=state.chat_history_id,
                        change=change_record,
                        db=db
                    )
                    tracked_changes.append({
                        "change_id": add_result.get("change_id", "CHG-XXX"),
                        "content": suggestion_content
                    })
                except Exception as e:
                    logger.error(f"Failed to track suggestion: {str(e)}")

        # Offer implicit suggestions
        if implicit_suggestions:
            first_implicit = implicit_suggestions[0]
            action_id = await state.add_pending_action(
                action_type="suggestion",
                content=first_implicit.get("content", ""),
                db=db,
                context="Implicit suggestion from hybrid query",
                category=first_implicit.get("action", "modify_architecture")
            )
            pending_suggestion = {
                "action_id": action_id,
                "content": first_implicit.get("content", ""),
                "awaiting_confirmation": True
            }

        # Add tracking info to response
        if tracked_changes:
            from database_scripts import get_pending_changes
            pending_count = len(await get_pending_changes(state.chat_history_id, db))
            response += f"\n\nI've captured your suggestion as **{tracked_changes[0]['change_id']}** ({pending_count} pending total)."

        return {
            "message": response,
            "action": "hybrid_query_processed",
            "action_reason": f"Answered question and processed {len(tracked_changes)} suggestions",
            "tracked_changes": tracked_changes,
            "pending_suggestion": pending_suggestion,
            "type": "hybrid_response"
        }


class PendingChangeManagementHandler(IntentHandler):
    """
    Handles intelligent management of pending changes.

    Supports dynamic actions like:
    - Finding duplicates
    - Merging similar changes
    - Removing specific changes
    - Consolidating multiple changes

    This handler creates pending actions for confirmations, ensuring
    users can approve/decline operations using semantic responses
    (not just "yes/no" keywords).
    """

    async def handle(
        self,
        classification: Dict[str, Any],
        state: ConversationState,
        context: Dict[str, Any],
        db: Session
    ) -> Dict[str, Any]:
        intents = classification.get("intents", [])
        command_intents = [i for i in intents if i.get("type") == "command"]

        if not command_intents:
            return await self._handle_general_management(classification, state, context, db)

        command_action = command_intents[0].get("action", "")
        change_ids = command_intents[0].get("change_ids", [])

        # Route to specific handler
        handlers = {
            "identify_duplicates": self._handle_identify_duplicates,
            "merge_changes": self._handle_merge_changes,
            "remove_changes": self._handle_remove_changes,
            "consolidate_changes": self._handle_consolidate,
            "show_change_details": self._handle_show_details
        }

        handler = handlers.get(command_action, self._handle_general_management)
        return await handler(classification, state, context, db, change_ids)

    async def _handle_identify_duplicates(
        self,
        classification: Dict[str, Any],
        state: ConversationState,
        context: Dict[str, Any],
        db: Session,
        change_ids: List[str] = None
    ) -> Dict[str, Any]:
        """Find and present duplicate changes, creating pending actions for merge."""
        from database_scripts import get_pending_changes, find_duplicate_changes

        changes = await get_pending_changes(state.chat_history_id, db)

        if not changes:
            return {
                "message": "You have no pending changes to check for duplicates.",
                "action": "identify_duplicates",
                "action_reason": "No pending changes found"
            }

        duplicates = await find_duplicate_changes(changes, threshold=0.5)

        if not duplicates:
            return {
                "message": f"I've checked your {len(changes)} pending change(s) and found no duplicates. Each change appears to be unique.",
                "action": "identify_duplicates",
                "action_reason": "No duplicates found"
            }

        # Create pending actions for each duplicate group
        pending_actions_created = []
        for group in duplicates:
            # Build a merged content suggestion
            merged_content = self._create_merged_content_from_ids(changes, group["ids"])

            action_id = await state.add_pending_action(
                action_type="merge_duplicates",
                content=f"Merge into: {merged_content}",
                db=db,
                context=f"Duplicate changes: {', '.join(group['ids'])}",
                category="pending_change_management"
            )
            pending_actions_created.append({
                "action_id": action_id,
                "change_ids": group["ids"],
                "merged_content": merged_content,
                "similarity": group["similarity"]
            })

        # Format response
        message = self._format_duplicate_findings(duplicates, pending_actions_created, changes)

        return {
            "message": message,
            "action": "duplicates_identified",
            "action_reason": f"Found {len(duplicates)} duplicate group(s)",
            "duplicate_groups": duplicates,
            "pending_actions": pending_actions_created
        }

    async def _handle_merge_changes(
        self,
        classification: Dict[str, Any],
        state: ConversationState,
        context: Dict[str, Any],
        db: Session,
        change_ids: List[str] = None
    ) -> Dict[str, Any]:
        """Propose merging specified changes into one."""
        from database_scripts import get_pending_changes

        # If no specific IDs provided, fall back to identifying duplicates
        if not change_ids or len(change_ids) < 2:
            logger.info("No specific change IDs for merge - falling back to duplicate identification")
            return await self._handle_identify_duplicates(classification, state, context, db, change_ids)

        changes = await get_pending_changes(state.chat_history_id, db)
        changes_to_merge = [c for c in changes if c.get('id') in change_ids]

        if len(changes_to_merge) < 2:
            found_ids = [c.get('id') for c in changes_to_merge]
            return {
                "message": f"I could only find {len(changes_to_merge)} of those changes ({found_ids}). Please check the change IDs.",
                "action": "merge_changes",
                "action_reason": "Not enough changes found"
            }

        # Create merged content suggestion
        merged_content = self._create_merged_content(changes_to_merge)

        # Create pending action for confirmation
        action_id = await state.add_pending_action(
            action_type="execute_merge",
            content=merged_content,
            db=db,
            context=f"Merging: {', '.join(change_ids)}",
            category="pending_change_management"
        )

        # Format the changes being merged
        changes_preview = "\n".join([
            f"- **{c.get('id')}**: {c.get('user_request', '')[:60]}..."
            for c in changes_to_merge
        ])

        return {
            "message": f"I'll merge these changes:\n\n{changes_preview}\n\nInto a single change:\n> {merged_content}\n\nShould I proceed with this merge?",
            "action": "merge_proposed",
            "action_reason": f"Proposing merge of {len(change_ids)} changes",
            "pending_suggestion": {
                "action_id": action_id,
                "change_ids": change_ids,
                "merged_content": merged_content,
                "awaiting_confirmation": True
            }
        }

    async def _handle_remove_changes(
        self,
        classification: Dict[str, Any],
        state: ConversationState,
        context: Dict[str, Any],
        db: Session,
        change_ids: List[str] = None
    ) -> Dict[str, Any]:
        """Propose removing specified changes."""
        from database_scripts import get_pending_changes

        if not change_ids:
            return {
                "message": "Please specify which change(s) to remove, e.g., 'remove CHG-001' or 'remove CHG-001 and CHG-002'.",
                "action": "remove_changes",
                "action_reason": "No change IDs specified"
            }

        changes = await get_pending_changes(state.chat_history_id, db)
        changes_to_remove = [c for c in changes if c.get('id') in change_ids]

        if not changes_to_remove:
            return {
                "message": f"I couldn't find those change(s). Your current pending changes are: {', '.join([c.get('id') for c in changes])}",
                "action": "remove_changes",
                "action_reason": "Changes not found"
            }

        # Create pending action for confirmation
        action_id = await state.add_pending_action(
            action_type="remove_changes",
            content=f"Remove changes: {', '.join(change_ids)}",
            db=db,
            context=f"Removing: {', '.join([c.get('user_request', '')[:30] for c in changes_to_remove])}",
            category="pending_change_management"
        )

        # Format the changes being removed
        changes_preview = "\n".join([
            f"- **{c.get('id')}**: {c.get('user_request', '')[:60]}..."
            for c in changes_to_remove
        ])

        return {
            "message": f"I'll remove these change(s):\n\n{changes_preview}\n\nShould I proceed?",
            "action": "remove_proposed",
            "action_reason": f"Proposing removal of {len(change_ids)} changes",
            "pending_suggestion": {
                "action_id": action_id,
                "change_ids": change_ids,
                "awaiting_confirmation": True
            }
        }

    async def _handle_consolidate(
        self,
        classification: Dict[str, Any],
        state: ConversationState,
        context: Dict[str, Any],
        db: Session,
        change_ids: List[str] = None
    ) -> Dict[str, Any]:
        """Analyze and propose consolidation of pending changes."""
        from database_scripts import get_pending_changes, find_duplicate_changes

        changes = await get_pending_changes(state.chat_history_id, db)

        if not changes:
            return {
                "message": "You have no pending changes to consolidate.",
                "action": "consolidate_changes",
                "action_reason": "No pending changes"
            }

        if len(changes) == 1:
            return {
                "message": f"You only have one pending change (**{changes[0].get('id')}**), so there's nothing to consolidate.",
                "action": "consolidate_changes",
                "action_reason": "Only one change"
            }

        # Find duplicates with lower threshold for consolidation
        duplicates = await find_duplicate_changes(changes, threshold=0.4)

        if duplicates:
            # Create pending action for each consolidation suggestion
            all_duplicate_ids = set()
            for group in duplicates:
                all_duplicate_ids.update(group["ids"])

            action_id = await state.add_pending_action(
                action_type="consolidate_all",
                content=f"Consolidate {len(all_duplicate_ids)} similar changes into fewer changes",
                db=db,
                context=f"Found {len(duplicates)} groups of similar changes",
                category="pending_change_management"
            )

            message = f"I analyzed your {len(changes)} pending changes and found some opportunities to consolidate:\n\n"

            for i, group in enumerate(duplicates, 1):
                message += f"**Group {i}** (similar changes):\n"
                for change_id in group["ids"]:
                    change = next((c for c in changes if c.get('id') == change_id), None)
                    if change:
                        message += f"- {change_id}: {change.get('user_request', '')[:50]}...\n"
                message += "\n"

            message += "Would you like me to merge these similar changes together?"

            return {
                "message": message,
                "action": "consolidation_proposed",
                "action_reason": f"Found {len(duplicates)} consolidation opportunities",
                "duplicate_groups": duplicates,
                "pending_suggestion": {
                    "action_id": action_id,
                    "awaiting_confirmation": True
                }
            }
        else:
            return {
                "message": f"I've analyzed your {len(changes)} pending changes and they all appear to be distinct. No consolidation needed.",
                "action": "consolidate_changes",
                "action_reason": "No consolidation opportunities"
            }

    async def _handle_show_details(
        self,
        classification: Dict[str, Any],
        state: ConversationState,
        context: Dict[str, Any],
        db: Session,
        change_ids: List[str] = None
    ) -> Dict[str, Any]:
        """Show details of a specific change."""
        from database_scripts import get_pending_changes

        if not change_ids:
            return {
                "message": "Please specify which change you want details for, e.g., 'show details of CHG-001'.",
                "action": "show_change_details",
                "action_reason": "No change ID specified"
            }

        changes = await get_pending_changes(state.chat_history_id, db)
        target_change = next((c for c in changes if c.get('id') == change_ids[0]), None)

        if not target_change:
            return {
                "message": f"I couldn't find change **{change_ids[0]}**. Your current changes are: {', '.join([c.get('id') for c in changes])}",
                "action": "show_change_details",
                "action_reason": "Change not found"
            }

        # Format detailed view
        details = f"""**{target_change.get('id')}**

**Request:** {target_change.get('user_request', 'N/A')}

**Type:** {target_change.get('type', 'modify_architecture')}

**Affected Sections:** {', '.join(target_change.get('affected_sections', ['general']))}

**Added:** {target_change.get('timestamp', 'Unknown')}

**Status:** {target_change.get('status', 'pending')}"""

        if target_change.get('merged_from'):
            details += f"\n\n**Merged From:** {', '.join(target_change.get('merged_from', []))}"

        return {
            "message": details,
            "action": "show_change_details",
            "action_reason": f"Showing details for {change_ids[0]}",
            "change": target_change
        }

    async def _handle_general_management(
        self,
        classification: Dict[str, Any],
        state: ConversationState,
        context: Dict[str, Any],
        db: Session,
        change_ids: List[str] = None
    ) -> Dict[str, Any]:
        """General pending change management when specific action is unclear.

        This is called when the semantic classifier routes to manage_pending_changes
        but doesn't specify a particular action. We show available options.
        NO keyword matching - trust the classifier's routing decision.
        """
        from database_scripts import get_pending_changes

        changes = await get_pending_changes(state.chat_history_id, db)

        if not changes:
            return {
                "message": "You have no pending changes. As you suggest modifications, I'll track them here.",
                "action": "pending_change_management",
                "action_reason": "No pending changes"
            }

        changes_list = "\n".join([
            f"- **{c.get('id')}**: {c.get('user_request', '')[:60]}..."
            for c in changes
        ])

        return {
            "message": f"You have {len(changes)} pending change(s):\n\n{changes_list}\n\nYou can:\n- Say **'find duplicates'** to identify similar changes\n- Say **'merge CHG-001 and CHG-002'** to combine changes\n- Say **'remove CHG-001'** to delete a change\n- Say **'what is CHG-001?'** for details",
            "action": "pending_change_management",
            "action_reason": f"Showing {len(changes)} changes with management options"
        }

    def _create_merged_content(self, changes: List[Dict]) -> str:
        """Create a merged content string from multiple changes."""
        if not changes:
            return ""

        if len(changes) == 1:
            return changes[0].get('user_request', '')

        # Combine the user requests intelligently
        requests = [c.get('user_request', '') for c in changes]

        # Simple approach: take the longest one as base
        base_request = max(requests, key=len)

        # If all requests are similar, just use the base
        return base_request

    def _create_merged_content_from_ids(self, all_changes: List[Dict], change_ids: List[str]) -> str:
        """Create merged content from change IDs."""
        changes_to_merge = [c for c in all_changes if c.get('id') in change_ids]
        return self._create_merged_content(changes_to_merge)

    def _format_duplicate_findings(
        self,
        duplicates: List[Dict],
        pending_actions: List[Dict],
        all_changes: List[Dict]
    ) -> str:
        """Format duplicate findings as a readable message."""
        message = f"I found **{len(duplicates)} group(s)** of similar changes:\n\n"

        for i, (group, action) in enumerate(zip(duplicates, pending_actions), 1):
            similarity_pct = int(group["similarity"] * 100)
            message += f"**Group {i}** ({similarity_pct}% similar) - Action: {action['action_id']}\n"

            for change_id in group["ids"]:
                change = next((c for c in all_changes if c.get('id') == change_id), None)
                if change:
                    message += f"  - {change_id}: {change.get('user_request', '')[:50]}...\n"

            message += f"  → Can merge into: \"{action['merged_content'][:60]}...\"\n\n"

        message += "Would you like me to merge these? You can say:\n"
        message += "- **'yes, merge them all'** to merge all duplicate groups\n"
        message += "- **'merge group 1'** to merge a specific group\n"
        message += "- **'no, keep them separate'** to leave as-is"

        return message


class UndoRedoHandler(IntentHandler):
    """
    Handles undo and redo operations for pending changes.

    Uses the transaction history to reverse or restore changes.
    Supports:
    - Undo last change: "undo", "undo that", "take that back"
    - Undo specific: "undo CHG-003", "remove CHG-001"
    - Redo: "redo", "bring that back"
    """

    async def handle(
        self,
        classification: Dict[str, Any],
        state: ConversationState,
        context: Dict[str, Any],
        db: Session
    ) -> Dict[str, Any]:
        from database_scripts import (
            undo_last_transaction,
            undo_specific_transaction,
            redo_last_transaction,
            remove_pending_change,
            add_pending_change,
            get_pending_changes,
            record_transaction
        )

        primary_intent = classification.get("primary_intent", "")
        intents = classification.get("intents", [])
        chat_history_id = context.get("chat_history_id", "")

        # Determine if this is undo or redo
        is_undo = primary_intent == "undo_request" or any(
            i.get("type") == "undo_request" for i in intents
        )
        is_redo = primary_intent == "redo_request" or any(
            i.get("type") == "redo_request" for i in intents
        )

        if is_undo:
            return await self._handle_undo(classification, chat_history_id, db)
        elif is_redo:
            return await self._handle_redo(classification, chat_history_id, db)
        else:
            return {
                "message": "I'm not sure what you want me to undo or redo. You can say 'undo' to undo the last change, 'undo CHG-003' to undo a specific change, or 'redo' to restore an undone change.",
                "action": "undo_redo_clarification",
                "action_reason": "Unclear undo/redo request"
            }

    async def _handle_undo(
        self,
        classification: Dict[str, Any],
        chat_history_id: str,
        db: Session
    ) -> Dict[str, Any]:
        from database_scripts import (
            undo_last_transaction,
            undo_specific_transaction,
            remove_pending_change,
            get_pending_changes
        )

        intents = classification.get("intents", [])

        # Check if a specific change ID was mentioned
        target_change_id = None
        for intent in intents:
            if intent.get("type") == "undo_request":
                target = intent.get("target", "")
                change_ids = intent.get("change_ids", [])
                if change_ids:
                    target_change_id = change_ids[0]
                elif target and target.upper().startswith("CHG-"):
                    target_change_id = target.upper()

        if target_change_id:
            # Undo specific change
            result = await undo_specific_transaction(chat_history_id, target_change_id, db)
        else:
            # Undo last change
            result = await undo_last_transaction(chat_history_id, db)

        if result["status"] == "success":
            # Actually reverse the action based on type
            action_type = result.get("action_type")
            action_data = result.get("action_data", {})

            if action_type == "add_change":
                # Remove the change that was added
                change_id = action_data.get("change_id")
                if change_id:
                    removal = await remove_pending_change(chat_history_id, change_id, db)
                    if removal.get("status") == "success":
                        return {
                            "message": f"Done! I've undone {change_id}: \"{action_data.get('user_request', '')[:50]}...\"\n\nThis change has been removed from your pending modifications.",
                            "action": "undo_success",
                            "action_reason": f"Undid add_change for {change_id}",
                            "undone_change_id": change_id
                        }

            elif action_type == "remove_change":
                # Re-add the change that was removed
                change_data = action_data.get("change_data", {})
                if change_data:
                    from database_scripts import add_pending_change
                    add_result = await add_pending_change(chat_history_id, change_data, db)
                    if add_result.get("status") == "success":
                        return {
                            "message": f"Done! I've restored {change_data.get('id')}: \"{change_data.get('user_request', '')[:50]}...\"\n\nThis change is back in your pending modifications.",
                            "action": "undo_success",
                            "action_reason": f"Undid remove_change, restored {change_data.get('id')}",
                            "restored_change_id": change_data.get('id')
                        }

            elif action_type == "merge_changes":
                # This is complex - we need to un-merge
                # For now, just report that the merge was undone conceptually
                merged_ids = action_data.get("merged_ids", [])
                return {
                    "message": f"The merge of {', '.join(merged_ids)} has been marked as undone in the history. To fully restore the original changes, you may need to re-add them manually.",
                    "action": "undo_merge_partial",
                    "action_reason": "Merge undo requires manual restoration"
                }

            # Generic success message if we couldn't identify the specific action
            return {
                "message": f"Done! I've undone the last action: \"{result.get('description', 'Unknown action')}\"",
                "action": "undo_success",
                "action_reason": "Undid transaction"
            }

        elif result["status"] == "nothing_to_undo":
            return {
                "message": "There's nothing to undo. You haven't made any changes yet, or all changes have already been undone.",
                "action": "undo_nothing",
                "action_reason": "No transactions to undo"
            }

        elif result["status"] == "not_found":
            return {
                "message": f"I couldn't find that change to undo. {result.get('message', '')}",
                "action": "undo_not_found",
                "action_reason": "Target change not found"
            }

        else:
            return {
                "message": f"Sorry, I wasn't able to undo that. {result.get('message', 'Please try again.')}",
                "action": "undo_error",
                "action_reason": f"Undo failed: {result.get('message', 'Unknown error')}"
            }

    async def _handle_redo(
        self,
        classification: Dict[str, Any],
        chat_history_id: str,
        db: Session
    ) -> Dict[str, Any]:
        from database_scripts import (
            redo_last_transaction,
            add_pending_change,
            remove_pending_change
        )

        result = await redo_last_transaction(chat_history_id, db)

        if result["status"] == "success":
            action_type = result.get("action_type")
            action_data = result.get("action_data", {})

            if action_type == "add_change":
                # Re-add the change
                change_data = action_data.get("change_data", {})
                if change_data:
                    add_result = await add_pending_change(chat_history_id, change_data, db)
                    if add_result.get("status") == "success":
                        return {
                            "message": f"Done! I've restored {change_data.get('id')}: \"{change_data.get('user_request', '')[:50]}...\"\n\nThis change is back in your pending modifications.",
                            "action": "redo_success",
                            "action_reason": f"Redid add_change for {change_data.get('id')}",
                            "restored_change_id": change_data.get('id')
                        }

            elif action_type == "remove_change":
                # Re-remove the change
                change_id = action_data.get("change_id")
                if change_id:
                    removal = await remove_pending_change(chat_history_id, change_id, db)
                    if removal.get("status") == "success":
                        return {
                            "message": f"Done! I've re-removed {change_id} as you originally requested.",
                            "action": "redo_success",
                            "action_reason": f"Redid remove_change for {change_id}",
                            "removed_change_id": change_id
                        }

            # Generic success
            return {
                "message": f"Done! I've redone the action: \"{result.get('description', 'Unknown action')}\"",
                "action": "redo_success",
                "action_reason": "Redid transaction"
            }

        elif result["status"] == "nothing_to_redo":
            return {
                "message": "There's nothing to redo. You haven't undone any changes recently.",
                "action": "redo_nothing",
                "action_reason": "No undone transactions to redo"
            }

        else:
            return {
                "message": f"Sorry, I wasn't able to redo that. {result.get('message', 'Please try again.')}",
                "action": "redo_error",
                "action_reason": f"Redo failed: {result.get('message', 'Unknown error')}"
            }


class ReportComparisonHandler(IntentHandler):
    """
    Handles comparison between report versions and showing diffs.

    Supports:
    - Version comparison: "what changed between v1 and v3?"
    - Show diff: "show me what changed"
    - Section-specific: "how did architecture change?"
    """

    async def handle(
        self,
        classification: Dict[str, Any],
        state: ConversationState,
        context: Dict[str, Any],
        db: Session
    ) -> Dict[str, Any]:
        from database_scripts import (
            get_all_report_versions,
            get_report_diff,
            get_pending_changes
        )

        chat_history_id = context.get("chat_history_id", "")
        intents = classification.get("intents", [])

        # Extract version numbers if specified
        versions = []
        for intent in intents:
            if intent.get("type") == "comparison_question":
                versions = intent.get("versions", [])
                break

        # Get all versions to understand context
        all_versions = await get_all_report_versions(chat_history_id, db)

        if not all_versions:
            return {
                "message": "No report versions found. Please generate a report first.",
                "action": "comparison_no_versions",
                "action_reason": "No report versions exist"
            }

        # If no specific versions, show pending changes + overall summary
        if not versions or len(versions) < 2:
            pending = await get_pending_changes(chat_history_id, db)
            latest_version = all_versions[0] if all_versions else None

            if pending:
                message = f"**Current State Summary**\n\n"
                message += f"**Current Version:** {latest_version['version_number']}\n"
                message += f"**Total Versions:** {len(all_versions)}\n\n"
                message += f"**Pending Changes ({len(pending)}):**\n"
                for change in pending:
                    message += f"- {change.get('id')}: {change.get('user_request', '')[:60]}...\n"
                message += f"\nThese changes are pending and will be applied when you regenerate the report.\n\n"
                message += f"To compare specific versions, say 'compare v1 to v{latest_version['version_number']}'"
            else:
                message = f"**Current State Summary**\n\n"
                message += f"**Current Version:** {latest_version['version_number']}\n"
                message += f"**Total Versions:** {len(all_versions)}\n"
                message += f"**Pending Changes:** None\n\n"
                if len(all_versions) > 1:
                    message += f"To see what changed between versions, say 'compare v1 to v{latest_version['version_number']}'"

            return {
                "message": message,
                "action": "comparison_summary",
                "action_reason": "Showed current state summary"
            }

        # Compare two specific versions
        try:
            version_a = int(versions[0]) if str(versions[0]).isdigit() else 1
            version_b = int(versions[1]) if str(versions[1]).isdigit() else all_versions[0]["version_number"]

            diff_result = await get_report_diff(chat_history_id, version_a, version_b, db)

            stats = diff_result.get("stats", {})
            message = f"**Comparison: Version {version_a} → Version {version_b}**\n\n"
            message += f"**Changes:**\n"
            message += f"- Lines added: +{stats.get('lines_added', 0)}\n"
            message += f"- Lines removed: -{stats.get('lines_removed', 0)}\n"
            message += f"- Total lines: {stats.get('lines_in_a', 0)} → {stats.get('lines_in_b', 0)}\n\n"

            if diff_result.get("summary_a") and diff_result.get("summary_b"):
                message += f"**Executive Summary Changes:**\n"
                message += f"- V{version_a}: {diff_result['summary_a'][:100]}...\n"
                message += f"- V{version_b}: {diff_result['summary_b'][:100]}...\n"

            return {
                "message": message,
                "action": "comparison_diff",
                "action_reason": f"Compared v{version_a} to v{version_b}",
                "diff_stats": stats
            }

        except Exception as e:
            logger.error(f"Error comparing versions: {str(e)}")
            return{
                "message": f"I couldn't compare those versions. Make sure both version numbers exist. Available versions: {', '.join('v' + str(v['version_number']) for v in all_versions)}",
                "action": "comparison_error",
                "action_reason": f"Comparison failed: {str(e)}"
            }


class WhatIfHandler(IntentHandler):
    """
    Handles hypothetical scenario analysis without committing changes.

    The user wants to understand the impact of a change before deciding.
    """

    async def handle(
        self,
        classification: Dict[str, Any],
        state: ConversationState,
        context: Dict[str, Any],
        db: Session
    ) -> Dict[str, Any]:
        from utils.router_llm import generate_router_llm_response

        intents = classification.get("intents", [])
        report_summary = context.get("report_summary", {})

        # Extract the scenario
        scenario = ""
        for intent in intents:
            if intent.get("type") == "whatif_question":
                scenario = intent.get("scenario", intent.get("content", ""))
                break

        if not scenario:
            return {
                "message": "What scenario would you like me to analyze? For example, 'What if we used PostgreSQL instead of DynamoDB?'",
                "action": "whatif_clarification",
                "action_reason": "No scenario specified"
            }

        # Generate impact analysis using LLM
        analysis_prompt = f"""Analyze this hypothetical scenario for the current architecture:

SCENARIO: {scenario}

CURRENT ARCHITECTURE SUMMARY:
{report_summary.get('executive_summary', 'No summary available')}

KEY TECHNOLOGIES:
{report_summary.get('key_technologies', [])}

Provide a brief impact analysis covering:
1. **Affected Components**: Which parts of the system would change?
2. **Estimated Effort**: Rough impact on timeline/cost (low/medium/high)
3. **Trade-offs**: What would be gained vs lost?
4. **Recommendation**: Brief recommendation on whether this change makes sense

Keep the response concise (150-200 words). End by asking if the user wants to track this as an actual change."""

        try:
            analysis = await generate_router_llm_response(
                prompt=analysis_prompt,
                prompt_type="analysis"
            )

            return {
                "message": f"**What-If Analysis: {scenario}**\n\n{analysis}\n\n---\n*This is a hypothetical analysis. Say 'yes, track this change' if you want to proceed, or ask another question.*",
                "action": "whatif_analysis",
                "action_reason": f"Analyzed scenario: {scenario[:50]}...",
                "scenario": scenario,
                "analysis": analysis
            }

        except Exception as e:
            logger.error(f"Error in what-if analysis: {str(e)}")
            return {
                "message": f"I had trouble analyzing that scenario. Let me try to help:\n\n**Scenario:** {scenario}\n\nCould you rephrase or provide more context about what you'd like to understand?",
                "action": "whatif_error",
                "action_reason": f"Analysis failed: {str(e)}"
            }


class RequirementEditHandler(IntentHandler):
    """
    Handles editing of existing pending changes.

    Supports:
    - "change CHG-002 to say PostgreSQL"
    - "update CHG-001"
    - "reword the last change"
    """

    async def handle(
        self,
        classification: Dict[str, Any],
        state: ConversationState,
        context: Dict[str, Any],
        db: Session
    ) -> Dict[str, Any]:
        from database_scripts import (
            get_pending_changes,
            update_pending_change,
            record_transaction
        )

        chat_history_id = context.get("chat_history_id", "")
        intents = classification.get("intents", [])

        # Extract target change and new value
        target_id = None
        new_value = None

        for intent in intents:
            if intent.get("type") == "edit_requirement":
                target_id = intent.get("target")
                change_ids = intent.get("change_ids", [])
                if change_ids:
                    target_id = change_ids[0]
                new_value = intent.get("new_value", intent.get("content", ""))

        # Get current pending changes
        pending = await get_pending_changes(chat_history_id, db)

        if not pending:
            return {
                "message": "There are no pending changes to edit. Make a suggestion first, then you can edit it.",
                "action": "edit_no_changes",
                "action_reason": "No pending changes exist"
            }

        # If no specific target, show available changes
        if not target_id:
            message = "Which change would you like to edit?\n\n"
            for change in pending:
                message += f"- **{change.get('id')}**: {change.get('user_request', '')[:50]}...\n"
            message += "\nSay 'edit CHG-001' to modify a specific change."

            return {
                "message": message,
                "action": "edit_select_target",
                "action_reason": "No target specified for edit"
            }

        # Find the target change
        target_change = next((c for c in pending if c.get('id') == target_id), None)

        if not target_change:
            return {
                "message": f"I couldn't find {target_id}. Available changes: {', '.join([c.get('id') for c in pending])}",
                "action": "edit_not_found",
                "action_reason": f"Change {target_id} not found"
            }

        # If no new value provided, show current and ask for new value
        if not new_value:
            return {
                "message": f"**Current {target_id}:**\n\n\"{target_change.get('user_request', '')}\"\n\nWhat would you like to change it to?",
                "action": "edit_awaiting_value",
                "action_reason": "Awaiting new value for edit",
                "editing_change_id": target_id
            }

        # Record the original for undo
        original_data = {
            "change_id": target_id,
            "original_request": target_change.get("user_request"),
            "new_request": new_value
        }
        await record_transaction(
            chat_history_id=chat_history_id,
            action_type="edit_change",
            action_data=original_data,
            description=f"Edited {target_id}",
            db=db
        )

        # Apply the edit
        update_result = await update_pending_change(
            chat_history_id=chat_history_id,
            change_id=target_id,
            updates={"user_request": new_value},
            db=db
        )

        if update_result.get("status") == "success":
            return {
                "message": f"Done! I've updated {target_id}.\n\n**Before:** \"{target_change.get('user_request', '')[:60]}...\"\n\n**After:** \"{new_value[:60]}...\"",
                "action": "edit_success",
                "action_reason": f"Edited {target_id}",
                "edited_change_id": target_id
            }
        else:
            return {
                "message": f"I couldn't update that change. {update_result.get('message', 'Please try again.')}",
                "action": "edit_error",
                "action_reason": f"Edit failed: {update_result.get('message', 'Unknown error')}"
            }


def get_intent_handler(primary_response_strategy: str) -> IntentHandler:
    """
    Get the appropriate handler for a response strategy.

    Args:
        primary_response_strategy: From semantic classification

    Returns:
        IntentHandler instance for that strategy
    """
    handlers = {
        # Confirmations
        "confirm_action": ConfirmationHandler(),
        "decline_action": DeclineHandler(),

        # Questions
        "answer_question": QuestionHandler(),
        "defend_architecture": ArchitectureChallengeHandler(),
        "compare_reports": ReportComparisonHandler(),
        "analyze_whatif": WhatIfHandler(),

        # Changes
        "track_change": SuggestionHandler(),
        "edit_requirement": RequirementEditHandler(),

        # Management
        "manage_pending_changes": PendingChangeManagementHandler(),
        "undo_redo": UndoRedoHandler(),
        "process_command": CommandHandler(),

        # Compound
        "hybrid_response": HybridQueryHandler()
    }

    return handlers.get(primary_response_strategy, QuestionHandler())
