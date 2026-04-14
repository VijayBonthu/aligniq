from sqlalchemy import Column, String, Integer, Float, create_engine, ForeignKey, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from config import settings
import uuid
from sqlalchemy.sql.sqltypes import TIMESTAMP
from sqlalchemy.sql.expression import text
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy import Column, String, DateTime, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

Base = declarative_base()
engine = create_engine(settings.DATABASE_URL)
sessionlocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = sessionlocal()
    try:
        yield db
    finally:
        db.close()


class SessionStatus:
    CREATED = "created"
    UPLOADED = "uploaded"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    
class Session(Base):
    __tablename__ = "sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    status = Column(String(50), nullable=False, default=SessionStatus.CREATED, index=True)
    
    document_name = Column(String(255))
    document_path = Column(String(512))
    
    job_id = Column(String(255))  # Celery task ID
    error_message = Column(Text)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    
    cancellation_reason = Column(String(255))
    processing_duration = Column(Integer)

class User(Base):
    __tablename__= "users"
    user_id = Column(String, primary_key=True, nullable=False, index=True,default=lambda: str(uuid.uuid4()))
    oauth_id = Column(String,unique=True, index=True)
    email_address = Column(String, nullable=False, unique=True, index=True)
    full_name = Column(String, nullable=False)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    verified_email = Column(Boolean, nullable=False)
    picture = Column(String) 
    provider = Column(String, nullable=False) 
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default= text('now()'))

class LoginDetails(Base):
    __tablename__="login_details"
    id = Column(Integer, primary_key=True, nullable=False, index=True)
    user_id = Column(String,ForeignKey(User.user_id), nullable=False,index=True, unique=True)
    hashed_password = Column(String, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default= text("now()"))

class UserDocuments(Base):
    __tablename__ = "user_documents"
    document_id = Column(String, primary_key=True, nullable=False,index=True,default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey(User.user_id), nullable=False, index=True)
    document_path = Column(String, nullable=False)
    active_tag = Column(Boolean, nullable=False, default=text("True"))
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))

class ChatHistory(Base):
    __tablename__ = "chat_history"
    chat_history_id = Column(String, primary_key=True, nullable=False, index=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String,ForeignKey(User.user_id), nullable=False,index=True)
    document_id = Column(String, ForeignKey(UserDocuments.document_id), nullable=False, index=True)
    active_tag = Column(Boolean, nullable=False, default=text("True"))
    title = Column(String, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))
    modified_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))
    message = Column(String, nullable=False)
    

class SelectedChat(Base):
    __tablename__ = "selected_chat"
    selected_chat_id = Column(String, primary_key=True, nullable=False, index=True, default=lambda: str(uuid.uuid4()))
    chat_history_id = Column(String, ForeignKey(ChatHistory.chat_history_id), nullable=False, index=True)
    document_id = Column(String, ForeignKey(UserDocuments.document_id), nullable=False, index=True)
    user_id = Column(String, ForeignKey(User.user_id), nullable=False, index=True)
    title = Column(String, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))
    modified_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))
    message = Column(String, nullable=False)

class ReportVersions(Base):
    __tablename__ = "report_version"
    report_version_id = Column(String, primary_key=True, nullable=False, index=True, default=lambda:str(uuid.uuid4()))
    chat_history_id = Column(String, ForeignKey(ChatHistory.chat_history_id), nullable=False, index=True)
    user_id = Column(String, ForeignKey(User.user_id), nullable=False, index=True)
    version_number = Column(Integer, nullable=False, default=1, index=True)
    report_content = Column(String, nullable=False)
    summary_report = Column(JSON, nullable=False)
    pending_changes = Column(JSON, nullable=True, default=[])  # Track modifications before regeneration
    schema_version = Column(String, nullable=False, default="1.0")  # For future migrations
    is_default = Column(Boolean, nullable=False, default=False, index=True)  # Mark as default/recommended version
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = Column(TIMESTAMP(timezone=True), nullable=True, onupdate=text("now()"))


# ============================================================================
# PENDING ACTIONS FOR CONVERSATION STATE MANAGEMENT
# ============================================================================

class PendingActionType:
    """Types of pending actions that can await user confirmation"""
    SUGGESTION = "suggestion"             # Architecture/requirement suggestion
    ROLLBACK = "rollback"                 # Rollback to previous version
    CLEAR_ALL = "clear_all"               # Clear all pending changes
    CONFIRMATION_REQUEST = "confirmation_request"  # Generic confirmation request


class PendingActionResolution:
    """Resolution statuses for pending actions"""
    CONFIRMED = "confirmed"
    DECLINED = "declined"
    EXPIRED = "expired"
    SUPERSEDED = "superseded"


class PendingAction(Base):
    """
    Tracks pending actions awaiting user confirmation in chat conversations.

    Replaces fragile string-based extraction with explicit state tracking.
    Each pending action has a unique ID (PA-001, PA-002, etc.) that the
    semantic classifier uses to map confirmations to specific actions.
    """
    __tablename__ = "pending_actions"

    id = Column(String(50), primary_key=True, nullable=False)  # Format: PA-001
    chat_history_id = Column(String, ForeignKey(ChatHistory.chat_history_id),
                             nullable=False, index=True)

    # Action details
    action_type = Column(String(50), nullable=False)  # suggestion, rollback, clear_all
    content = Column(Text, nullable=False)  # What the action does
    context = Column(Text, nullable=True)   # Why this was offered
    category = Column(String(50), nullable=True)  # modify_architecture, modify_requirements, etc.

    # State
    awaiting_response = Column(Boolean, nullable=False, default=True, index=True)

    # Resolution (when resolved)
    resolution = Column(String(50), nullable=True)  # confirmed, declined, expired, superseded
    resolution_message = Column(Text, nullable=True)  # Conditions or notes
    resolved_at = Column(TIMESTAMP(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))


# ============================================================================
# PRE-SALES WORKFLOW MODELS
# ============================================================================

class PresalesStatus:
    """Status options for pre-sales analysis"""
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class PresalesAnalysis(Base):
    """
    Stores pre-sales analysis results.

    This is the fast initial scan (60-120 sec) that identifies:
    - Key requirements from the document
    - Blind spots and underestimations
    - Technology risks
    - Kickstart questions for the client
    """
    __tablename__ = "presales_analysis"

    presales_id = Column(String, primary_key=True, nullable=False, index=True,
                         default=lambda: str(uuid.uuid4()))
    document_id = Column(String, ForeignKey(UserDocuments.document_id),
                         nullable=False, index=True)
    user_id = Column(String, ForeignKey(User.user_id), nullable=False, index=True)

    # Analysis outputs (JSON)
    extracted_requirements = Column(JSON, nullable=True)  # From scanner agent
    blind_spots = Column(JSON, nullable=True)             # From blind spot detector
    p1_blockers = Column(JSON, nullable=True)             # P1 blockers with questions
    technology_risks = Column(JSON, nullable=True)        # Tech risks identified by LLM
    kickstart_questions = Column(JSON, nullable=True)     # Critical questions (critical_unknowns)

    # Final brief (markdown)
    presales_brief = Column(Text, nullable=True)

    # Metadata
    status = Column(String(50), nullable=False, default=PresalesStatus.PROCESSING)
    model_used = Column(String(100), nullable=True)       # e.g., "gpt-4o-mini"
    processing_time_seconds = Column(Integer, nullable=True)

    # Readiness tracking (populated after answer analysis)
    iteration_count = Column(Integer, default=1)
    readiness_score = Column(Float, default=0.0)          # 0.0 to 1.0
    readiness_status = Column(String(50), default='not_analyzed')
    # Values: 'not_analyzed', 'needs_more_info', 'ready_with_assumptions', 'ready'
    assumptions_list = Column(JSON, default=list)          # Assumptions to be made
    contradictions_list = Column(JSON, default=list)       # Contradictions found
    vague_answers_list = Column(JSON, default=list)        # Vague answers needing clarification

    created_at = Column(TIMESTAMP(timezone=True), nullable=False,
                        server_default=text("now()"))
    updated_at = Column(TIMESTAMP(timezone=True), nullable=True,
                        onupdate=text("now()"))


class RaisedTechnologyRisk(Base):
    """
    Passively captures technology risks raised by the LLM.

    This data is collected for future analysis:
    - Which risks are raised most often?
    - Which risks were actually relevant?
    - Can we improve prompts based on feedback?

    The LLM raises risks based on its training data. Pre-sales flags them,
    Solution Architect validates. This table captures that data.
    """
    __tablename__ = "raised_technology_risks"

    risk_id = Column(String, primary_key=True, nullable=False, index=True,
                     default=lambda: str(uuid.uuid4()))
    presales_id = Column(String, ForeignKey(PresalesAnalysis.presales_id),
                         nullable=False, index=True)
    document_id = Column(String, ForeignKey(UserDocuments.document_id),
                         nullable=False, index=True)
    user_id = Column(String, ForeignKey(User.user_id), nullable=False, index=True)

    # Risk details
    technologies = Column(JSON, nullable=True)            # ["Power BI", "iframe", "API"]
    risk_title = Column(String(500), nullable=False)      # Short title
    risk_description = Column(Text, nullable=True)        # Full description
    severity = Column(String(50), nullable=True)          # critical, high, medium, low
    category = Column(String(100), nullable=True)         # integration, performance, security, etc.

    # Optional feedback (SA can mark if risk was actually relevant)
    was_relevant = Column(Boolean, nullable=True)         # True = real issue, False = not applicable
    user_feedback = Column(Text, nullable=True)           # Notes from SA/user

    # Metadata
    model_used = Column(String(100), nullable=True)       # Model that raised this risk
    created_at = Column(TIMESTAMP(timezone=True), nullable=False,
                        server_default=text("now()"))


class AnalysisLink(Base):
    """
    Links pre-sales analysis to full report generation.

    This allows:
    - Tracking the journey from pre-sales scan to full report
    - Storing user answers to kickstart questions
    - Connecting the fast scan with the comprehensive analysis
    """
    __tablename__ = "analysis_links"

    link_id = Column(String, primary_key=True, nullable=False, index=True,
                     default=lambda: str(uuid.uuid4()))
    document_id = Column(String, ForeignKey(UserDocuments.document_id),
                         nullable=False, index=True)
    user_id = Column(String, ForeignKey(User.user_id), nullable=False, index=True)

    # Links to both analysis types
    presales_id = Column(String, ForeignKey(PresalesAnalysis.presales_id),
                         nullable=True, index=True)
    chat_history_id = Column(String, ForeignKey(ChatHistory.chat_history_id),
                             nullable=True, index=True)  # Full report chat

    # User answers to kickstart questions (if provided before full report)
    user_answers = Column(JSON, nullable=True)

    # Tracking flags
    full_report_requested = Column(Boolean, default=False)
    full_report_generated = Column(Boolean, default=False)

    created_at = Column(TIMESTAMP(timezone=True), nullable=False,
                        server_default=text("now()"))
    updated_at = Column(TIMESTAMP(timezone=True), nullable=True,
                        onupdate=text("now()"))


# =============================================================================
# QUESTION STATUS ENUM
# =============================================================================
class QuestionStatus:
    PENDING = "pending"           # No answer yet
    ANSWERED = "answered"         # Has answer
    INVALID = "invalid"           # No longer relevant
    NEEDS_REVIEW = "needs_review" # Restored or flagged for review


class QuestionType:
    P1_BLOCKER = "p1_blocker"
    KICKSTART = "kickstart"


class AnswerQuality:
    GOOD = "good"                 # Clear, useful answer
    VAGUE = "vague"               # Needs clarification
    CONTRADICTING = "contradicting"  # Conflicts with other answers


class PresalesQuestion(Base):
    """
    Tracks individual P1 blockers and kickstart questions with state management.

    Each question goes through a lifecycle:
    - PENDING: Initial state, no answer
    - ANSWERED: Has an answer (may be good, vague, or contradicting)
    - INVALID: Another answer made this question irrelevant
    - NEEDS_REVIEW: Restored from invalid or flagged for attention
    """
    __tablename__ = "presales_questions"

    question_id = Column(String, primary_key=True, nullable=False, index=True,
                         default=lambda: str(uuid.uuid4()))
    presales_id = Column(String, ForeignKey(PresalesAnalysis.presales_id),
                         nullable=False, index=True)
    user_id = Column(String, ForeignKey(User.user_id), nullable=False, index=True)

    # Question identification
    question_type = Column(String(20), nullable=False)    # 'p1_blocker' or 'kickstart'
    question_number = Column(String(10), nullable=False)  # 'P1-1', 'P1-2', 'Q1', etc.
    display_order = Column(Integer, nullable=False, default=0)

    # Question content (from blind spots analysis)
    area_or_category = Column(String(100), nullable=True)  # 'Integration', 'Security', etc.
    title = Column(String(500), nullable=True)             # Blocker title or main point
    description = Column(Text, nullable=True)              # why_it_matters or why_critical
    impact_description = Column(Text, nullable=True)       # impact_if_unknown
    question_text = Column(Text, nullable=False)           # The actual question to ask

    # Answer tracking
    answer = Column(Text, nullable=True)
    answer_quality = Column(String(20), nullable=True)     # 'good', 'vague', 'contradicting'
    answer_feedback = Column(Text, nullable=True)          # Feedback about answer quality
    answered_at = Column(TIMESTAMP(timezone=True), nullable=True)
    answered_by = Column(String, nullable=True)            # user_id who answered

    # State management
    status = Column(String(20), nullable=False, default=QuestionStatus.PENDING)

    # Invalidation tracking
    invalidated_reason = Column(Text, nullable=True)
    invalidated_at = Column(TIMESTAMP(timezone=True), nullable=True)
    invalidated_by_question_id = Column(String, nullable=True)  # Which question invalidated this

    # Iteration tracking
    created_in_iteration = Column(Integer, default=1)
    invalidated_in_iteration = Column(Integer, nullable=True)
    restored_in_iteration = Column(Integer, nullable=True)

    # Timestamps
    created_at = Column(TIMESTAMP(timezone=True), nullable=False,
                        server_default=text("now()"))
    updated_at = Column(TIMESTAMP(timezone=True), nullable=True,
                        onupdate=text("now()"))


class PresalesAnswerHistory(Base):
    """
    Audit trail for all answer changes.

    Tracks every modification to answers for:
    - Debugging and support
    - Understanding user behavior
    - Future collaborative features
    """
    __tablename__ = "presales_answer_history"

    history_id = Column(String, primary_key=True, nullable=False, index=True,
                        default=lambda: str(uuid.uuid4()))
    question_id = Column(String, ForeignKey(PresalesQuestion.question_id),
                         nullable=False, index=True)
    presales_id = Column(String, ForeignKey(PresalesAnalysis.presales_id),
                         nullable=False, index=True)

    # Change tracking
    previous_answer = Column(Text, nullable=True)
    new_answer = Column(Text, nullable=True)
    change_type = Column(String(20), nullable=False)  # 'created', 'updated', 'cleared'

    # Metadata
    changed_by = Column(String, nullable=False)       # user_id
    changed_at = Column(TIMESTAMP(timezone=True), nullable=False,
                        server_default=text("now()"))
    iteration_number = Column(Integer, nullable=True)


class PresalesAnalysisHistory(Base):
    """
    Tracks each analysis run for audit/debugging.

    Captures a snapshot of the analysis state at each iteration,
    allowing us to understand how the analysis evolved.
    """
    __tablename__ = "presales_analysis_history"

    analysis_history_id = Column(String, primary_key=True, nullable=False, index=True,
                                  default=lambda: str(uuid.uuid4()))
    presales_id = Column(String, ForeignKey(PresalesAnalysis.presales_id),
                         nullable=False, index=True)

    # Analysis snapshot
    iteration_number = Column(Integer, nullable=False)
    readiness_score = Column(Float, nullable=True)
    readiness_status = Column(String(50), nullable=True)

    # Analysis results
    assumptions_made = Column(JSON, nullable=True)
    contradictions_found = Column(JSON, nullable=True)
    vague_answers_found = Column(JSON, nullable=True)
    questions_invalidated = Column(JSON, nullable=True)  # Array of question_ids
    questions_added = Column(JSON, nullable=True)        # Array of new questions

    # Input snapshot
    answers_snapshot = Column(JSON, nullable=True)       # All answers at time of analysis

    # Metadata
    analyzed_at = Column(TIMESTAMP(timezone=True), nullable=False,
                         server_default=text("now()"))
    analyzed_by = Column(String, nullable=True)          # user_id who triggered
    processing_time_ms = Column(Integer, nullable=True)


# ============================================================================
# TRANSACTION HISTORY FOR UNDO/REDO OPERATIONS
# ============================================================================

class TransactionActionType:
    """Types of actions that can be undone/redone"""
    ADD_CHANGE = "add_change"           # Added a pending change
    REMOVE_CHANGE = "remove_change"     # Removed a pending change
    MERGE_CHANGES = "merge_changes"     # Merged multiple changes
    EDIT_CHANGE = "edit_change"         # Modified a change
    CONFIRM_ACTION = "confirm_action"   # Confirmed a pending action
    CLEAR_ALL = "clear_all"             # Cleared all changes


class TransactionHistory(Base):
    """
    Tracks all reversible actions for undo/redo functionality.

    Each transaction stores enough data to reverse the action.
    The undo/redo stacks are managed per chat session.
    """
    __tablename__ = "transaction_history"

    id = Column(String, primary_key=True, nullable=False, index=True,
                default=lambda: str(uuid.uuid4()))
    chat_history_id = Column(String, ForeignKey(ChatHistory.chat_history_id),
                             nullable=False, index=True)

    # Action details
    action_type = Column(String(50), nullable=False)  # add_change, remove_change, merge, etc.
    action_description = Column(Text, nullable=True)   # Human-readable description

    # Data to reverse/redo the action (JSON)
    # For add_change: {"change_id": "CHG-001", "change_data": {...}}
    # For remove_change: {"change_id": "CHG-001", "change_data": {...}}
    # For merge: {"merged_ids": ["CHG-001", "CHG-002"], "result_id": "CHG-003", "original_data": [...]}
    action_data = Column(JSON, nullable=False)

    # Stack position (for ordering undo/redo)
    sequence_number = Column(Integer, nullable=False, index=True)

    # State tracking
    is_undone = Column(Boolean, nullable=False, default=False, index=True)
    undone_at = Column(TIMESTAMP(timezone=True), nullable=True)
    redone_at = Column(TIMESTAMP(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(TIMESTAMP(timezone=True), nullable=False,
                        server_default=text("now()"))