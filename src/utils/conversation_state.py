"""
Conversation State Management

Provides explicit state tracking for chat conversations, replacing fragile
string-based pending action extraction with database-backed state management.

Key Classes:
- PendingActionState: Dataclass for in-memory representation of pending actions
- ConversationState: Manages the full conversation state including pending actions

Usage:
    # Load state at start of request
    state = await load_conversation_state(chat_history_id, db)

    # Add a pending action
    action_id = await state.add_pending_action(
        action_type="suggestion",
        content="Use PostgreSQL instead of MongoDB",
        context="User asked about database options",
        category="modify_architecture",
        db=db
    )

    # Resolve a pending action
    await state.resolve_pending_action(
        action_id="PA-001",
        resolution="confirmed",
        resolution_message="User confirmed with no conditions",
        db=db
    )

    # Get active pending actions for classification
    active_actions = state.get_active_pending_actions()
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session
from utils.logger import logger


@dataclass
class PendingActionState:
    """
    In-memory representation of a pending action.

    This is used for passing state to the semantic classifier and handlers,
    separate from the SQLAlchemy model for clean separation of concerns.
    """
    action_id: str                      # "PA-001"
    action_type: str                    # "suggestion", "rollback", "clear_all"
    content: str                        # What the action does
    context: Optional[str] = None       # Why this was offered
    category: Optional[str] = None      # "modify_architecture", etc.
    created_at: Optional[datetime] = None
    awaiting_response: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "action_id": self.action_id,
            "action_type": self.action_type,
            "content": self.content,
            "context": self.context,
            "category": self.category,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "awaiting_response": self.awaiting_response
        }

    def to_classifier_format(self) -> Dict[str, Any]:
        """
        Format for the semantic classifier prompt.

        Returns a concise representation focused on what the classifier needs
        to understand and map confirmations to.
        """
        return {
            "id": self.action_id,
            "type": self.action_type,
            "content": self.content,
            "category": self.category
        }


@dataclass
class ConversationState:
    """
    Manages the full conversation state for a chat session.

    This class provides methods to:
    - Load pending actions from the database
    - Add new pending actions
    - Resolve pending actions (confirm/decline)
    - Get active pending actions for classification
    - Track changes for deduplication warnings
    """
    chat_history_id: str
    pending_actions: List[PendingActionState] = field(default_factory=list)
    _next_action_number: int = field(default=1, repr=False)
    _db: Optional[Session] = field(default=None, repr=False)

    async def load_from_db(self, db: Session) -> None:
        """
        Load pending actions from the database.

        This should be called at the start of each request to get the current state.
        """
        from models import PendingAction

        self._db = db
        self.pending_actions = []

        try:
            # Query all pending actions for this chat
            db_actions = db.query(PendingAction).filter(
                PendingAction.chat_history_id == self.chat_history_id
            ).order_by(PendingAction.created_at).all()

            max_number = 0
            for db_action in db_actions:
                # Track highest action number for generating new IDs
                try:
                    num = int(db_action.id.split('-')[1])
                    max_number = max(max_number, num)
                except (IndexError, ValueError):
                    pass

                # Convert to state object
                action_state = PendingActionState(
                    action_id=db_action.id,
                    action_type=db_action.action_type,
                    content=db_action.content,
                    context=db_action.context,
                    category=db_action.category,
                    created_at=db_action.created_at,
                    awaiting_response=db_action.awaiting_response
                )
                self.pending_actions.append(action_state)

            self._next_action_number = max_number + 1
            logger.info(f"Loaded {len(self.pending_actions)} pending actions for chat {self.chat_history_id}")

        except Exception as e:
            logger.error(f"Error loading pending actions: {str(e)}")
            # Start fresh if there's an error
            self.pending_actions = []
            self._next_action_number = 1

    async def add_pending_action(
        self,
        action_type: str,
        content: str,
        db: Session,
        context: Optional[str] = None,
        category: Optional[str] = None
    ) -> str:
        """
        Add a new pending action to the database and state.

        Args:
            action_type: Type of action (suggestion, rollback, clear_all)
            content: What the action does
            db: Database session
            context: Why this was offered
            category: Change category (modify_architecture, etc.)

        Returns:
            The action ID (e.g., "PA-001")
        """
        from models import PendingAction

        # Generate action ID
        action_id = f"PA-{self._next_action_number:03d}"
        self._next_action_number += 1

        try:
            # Create database record
            db_action = PendingAction(
                id=action_id,
                chat_history_id=self.chat_history_id,
                action_type=action_type,
                content=content,
                context=context,
                category=category,
                awaiting_response=True
            )
            db.add(db_action)
            db.commit()

            # Add to in-memory state
            action_state = PendingActionState(
                action_id=action_id,
                action_type=action_type,
                content=content,
                context=context,
                category=category,
                created_at=datetime.now(),
                awaiting_response=True
            )
            self.pending_actions.append(action_state)

            logger.info(f"Added pending action {action_id}: {content[:50]}...")
            return action_id

        except Exception as e:
            logger.error(f"Error adding pending action: {str(e)}")
            db.rollback()
            raise

    async def resolve_pending_action(
        self,
        action_id: str,
        resolution: str,
        db: Session,
        resolution_message: Optional[str] = None
    ) -> Optional[PendingActionState]:
        """
        Resolve a pending action (confirm, decline, expire, supersede).

        Args:
            action_id: The action ID to resolve (e.g., "PA-001")
            resolution: The resolution type (confirmed, declined, expired, superseded)
            db: Database session
            resolution_message: Optional message about conditions or notes

        Returns:
            The resolved PendingActionState, or None if not found
        """
        from models import PendingAction

        try:
            # Update database
            db_action = db.query(PendingAction).filter(
                PendingAction.id == action_id,
                PendingAction.chat_history_id == self.chat_history_id
            ).first()

            if not db_action:
                logger.warning(f"Pending action {action_id} not found")
                return None

            db_action.awaiting_response = False
            db_action.resolution = resolution
            db_action.resolution_message = resolution_message
            db_action.resolved_at = datetime.now()
            db.commit()

            # Update in-memory state
            for action in self.pending_actions:
                if action.action_id == action_id:
                    action.awaiting_response = False
                    logger.info(f"Resolved pending action {action_id} as {resolution}")
                    return action

            return None

        except Exception as e:
            logger.error(f"Error resolving pending action: {str(e)}")
            db.rollback()
            raise

    async def resolve_all_pending(
        self,
        resolution: str,
        db: Session,
        resolution_message: Optional[str] = None
    ) -> int:
        """
        Resolve all pending actions at once (e.g., when user confirms all).

        Returns:
            Number of actions resolved
        """
        resolved_count = 0
        for action in self.get_active_pending_actions():
            await self.resolve_pending_action(
                action_id=action.action_id,
                resolution=resolution,
                db=db,
                resolution_message=resolution_message
            )
            resolved_count += 1
        return resolved_count

    def get_active_pending_actions(self) -> List[PendingActionState]:
        """Get only actions still awaiting response."""
        return [a for a in self.pending_actions if a.awaiting_response]

    def get_pending_action(self, action_id: str) -> Optional[PendingActionState]:
        """Get a specific pending action by ID."""
        for action in self.pending_actions:
            if action.action_id == action_id:
                return action
        return None

    def has_active_pending_actions(self) -> bool:
        """Check if there are any pending actions awaiting response."""
        return len(self.get_active_pending_actions()) > 0

    def get_pending_actions_for_classifier(self) -> List[Dict[str, Any]]:
        """
        Get pending actions formatted for the semantic classifier.

        Returns a list of dictionaries with the fields the classifier needs
        to understand what actions are awaiting confirmation.
        """
        active = self.get_active_pending_actions()
        return [action.to_classifier_format() for action in active]

    def format_pending_actions_summary(self) -> str:
        """
        Format pending actions as a human-readable summary.

        Used for including in assistant responses when listing pending actions.
        """
        active = self.get_active_pending_actions()
        if not active:
            return "No pending actions."

        lines = []
        for action in active:
            lines.append(f"- **{action.action_id}**: {action.content}")

        return "\n".join(lines)


async def load_conversation_state(chat_history_id: str, db: Session) -> ConversationState:
    """
    Load conversation state from the database.

    This is the main entry point for getting conversation state at the start
    of each request.

    Args:
        chat_history_id: The chat history ID to load state for
        db: Database session

    Returns:
        ConversationState with pending actions loaded from DB
    """
    state = ConversationState(chat_history_id=chat_history_id)
    await state.load_from_db(db)
    return state


def warn_if_similar_change(new_request: str, existing_changes: List[Dict]) -> Optional[str]:
    """
    Check if a new change request is similar to existing ones.

    Uses simple word overlap (no embeddings) to detect potential duplicates.
    Returns a warning message if similar change found, None otherwise.

    Args:
        new_request: The new change request text
        existing_changes: List of existing change dicts with 'user_request' field

    Returns:
        Warning message if similar change found, None otherwise
    """
    if not existing_changes:
        return None

    new_words = set(new_request.lower().split())
    if len(new_words) < 2:
        return None  # Too short to compare meaningfully

    for existing in existing_changes:
        existing_request = existing.get("user_request", "")
        if not existing_request:
            continue

        existing_words = set(existing_request.lower().split())
        if len(existing_words) < 2:
            continue

        # Calculate Jaccard similarity
        intersection = len(new_words & existing_words)
        union = len(new_words | existing_words)
        similarity = intersection / union if union > 0 else 0

        if similarity > 0.6:
            change_id = existing.get("id", existing.get("change_id", "unknown"))
            preview = existing_request[:50] + "..." if len(existing_request) > 50 else existing_request
            return f"Note: This seems similar to {change_id}: '{preview}'"

    return None
