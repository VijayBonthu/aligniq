from sqlalchemy import Column, String, Integer, Float, create_engine, ForeignKey, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from config import settings
import uuid
from sqlalchemy.sql.sqltypes import TIMESTAMP
from sqlalchemy.sql.expression import text
from sqlalchemy.dialects.postgresql import JSON, JSONB
from sqlalchemy import Column, String, DateTime, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from utils.ids import new_id, new_hex, uuid7

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

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid7)
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
    user_id = Column(String, primary_key=True, nullable=False, index=True,default=new_id)
    oauth_id = Column(String,unique=True, index=True)
    email_address = Column(String, nullable=False, unique=True, index=True)
    full_name = Column(String, nullable=False)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    verified_email = Column(Boolean, nullable=False)
    picture = Column(String)
    provider = Column(String, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default= text('now()'))
    # Extended profile fields (migration 010)
    username                 = Column(String(50), nullable=True, unique=True)
    role                     = Column(String(50), nullable=True)
    # Company / organization captured at signup (migration 0004)
    company                  = Column(String(120), nullable=True)
    # Subscription fields (migration 009)
    stripe_customer_id      = Column(String, nullable=True, unique=True, index=True)
    subscription_tier       = Column(String(50), nullable=False, server_default=text("'free'"))
    subscription_status     = Column(String(50), nullable=False, server_default=text("'active'"))
    stripe_subscription_id  = Column(String, nullable=True)
    subscription_period_end = Column(TIMESTAMP(timezone=True), nullable=True)
    # Backend comp/gift grants (no Stripe). An admin can grant any tier for N days;
    # get_effective_tier() in utils/subscription.py honors comp_tier while
    # comp_expires_at is in the future, then lazily reverts to subscription_tier.
    comp_tier               = Column(String(50), nullable=True)
    comp_expires_at         = Column(TIMESTAMP(timezone=True), nullable=True)
    # Firm membership (migration 019, Bet 3)
    firm_id                 = Column(String, ForeignKey("firms.firm_id"), nullable=True, index=True)
    firm_role               = Column(String(32), nullable=True)  # 'firm_admin' | 'member'
    # Platform (GroundedIQ) staff — gates the /admin ops console. Distinct from
    # firm_role (which is per-customer-firm). Migration 0010. Granted via the
    # X-Admin-Key break-glass endpoint /admin/set-staff.
    is_staff                = Column(Boolean, nullable=False, server_default=text("false"))

class LoginDetails(Base):
    __tablename__="login_details"
    id = Column(Integer, primary_key=True, nullable=False, index=True)
    user_id = Column(String,ForeignKey(User.user_id), nullable=False,index=True, unique=True)
    hashed_password = Column(String, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default= text("now()"))

class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    id = Column(Integer, primary_key=True, nullable=False, index=True)
    user_id = Column(String, ForeignKey(User.user_id), nullable=False, index=True)
    token_hash = Column(String, nullable=False, unique=True)
    expires_at = Column(TIMESTAMP(timezone=True), nullable=False)
    revoked = Column(Boolean, nullable=False, default=False)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))

class UserIdentity(Base):
    """One row per external login method linked to a user — Google / GitHub / Microsoft /
    Local. Lets the backend know which methods unlock an account, distinguish the login
    method per session, and power a future Connected-accounts / unlink UI. Enforced
    one-per-(user, provider) in code (record_identity). `provider_user_id` is the OAuth
    `sub`/id (or the user_id for Local)."""
    __tablename__ = "user_identities"
    id = Column(Integer, primary_key=True, nullable=False, index=True)
    user_id = Column(String, ForeignKey(User.user_id), nullable=False, index=True)
    provider = Column(String(32), nullable=False, index=True)
    provider_user_id = Column(String, nullable=True)
    email = Column(String, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))

class SignupEvent(Base):
    """One row per account creation — the anti-abuse audit trail. Captures the signup
    IP (cf-connecting-ip), the FingerprintJS device id (null for OAuth popups), UA and
    provider. `flagged` is set when device/IP velocity over 24h exceeds the soft-flag
    thresholds (review signal only — never blocks)."""
    __tablename__ = "signup_events"
    id = Column(Integer, primary_key=True, nullable=False, index=True)
    user_id = Column(String, ForeignKey(User.user_id), nullable=True, index=True)
    email = Column(String, nullable=True, index=True)
    ip = Column(String, nullable=True, index=True)
    device_id = Column(String, nullable=True, index=True)
    user_agent = Column(String, nullable=True)
    provider = Column(String(32), nullable=True)
    flagged = Column(Boolean, nullable=False, default=False)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))

class JiraCredential(Base):
    """Server-side Jira OAuth tokens — one row per app user. The Atlassian access token
    is short-lived (~1h) and refreshed in place via the refresh token; no Jira token ever
    reaches the browser. Replaces the old client-held Jira JWT + Jira_Authorization header."""
    __tablename__ = "jira_credentials"
    user_id       = Column(String, ForeignKey(User.user_id), primary_key=True, index=True)
    access_token  = Column(Text, nullable=False)
    refresh_token = Column(Text, nullable=True)
    cloud_id      = Column(String, nullable=True)
    account_id    = Column(String, nullable=True)
    email         = Column(String, nullable=True)
    scope         = Column(Text, nullable=True)
    expires_at    = Column(TIMESTAMP(timezone=True), nullable=True)  # Atlassian access-token expiry
    created_at    = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))
    updated_at    = Column(TIMESTAMP(timezone=True), nullable=True, onupdate=func.now())

class UsageTracking(Base):
    __tablename__ = "usage_tracking"
    id                        = Column(Integer, primary_key=True, index=True)
    user_id                   = Column(String, ForeignKey("users.user_id"), nullable=False, index=True)
    period_start              = Column(TIMESTAMP(timezone=True), nullable=False)
    period_end                = Column(TIMESTAMP(timezone=True), nullable=False)
    report_regenerations_used = Column(Integer, nullable=False, default=0)
    # report_generations_used counts ALL full-report generations this period — the
    # initial generation AND every regeneration share one pool (closes the hole
    # where the first, most expensive, generation was uncounted). presales_used
    # meters the cheap presales brief separately. Both reset with the billing period.
    report_generations_used   = Column(Integer, nullable=False, server_default=text("0"))
    presales_used             = Column(Integer, nullable=False, server_default=text("0"))
    created_at                = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))
    updated_at                = Column(TIMESTAMP(timezone=True), nullable=True)

class ProcessedStripeEvent(Base):
    __tablename__ = "processed_stripe_events"
    # Stripe webhook idempotency. We record every event.id we have handled so a
    # redelivered/duplicated event is ignored. Handlers also set absolute state
    # (not increments), so reprocessing would be harmless even without this.
    event_id    = Column(String, primary_key=True, index=True)
    event_type  = Column(String(100), nullable=True)
    received_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))

class CreditWallet(Base):
    """Prepaid credit balance — the universal top-up across all tiers. Credits are
    spent when a tier's monthly allowance is exhausted (report generations,
    presales briefs). 1 credit = $0.10 of list value (see config.CREDIT_VALUE_USD);
    actions cost CREDIT_MULTIPLIER × COGS (see utils.subscription.CREDIT_COSTS).
    One row per user, created lazily on first grant/debit."""
    __tablename__ = "credit_wallet"
    user_id        = Column(String, ForeignKey(User.user_id), primary_key=True, index=True)
    balance_credits = Column(Integer, nullable=False, server_default=text("0"))
    updated_at     = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"), onupdate=func.now())

class CreditLedger(Base):
    """Append-only audit trail of every credit movement. Like llm_call_log, the
    scope refs are LOGICAL (no hard FK) so the ledger tolerates out-of-order
    writes and OUTLIVES the rows it references — a credit history must survive
    deletion of the project/report it paid for. delta is +grant / -debit."""
    __tablename__ = "credit_ledger"
    id          = Column(Integer, primary_key=True, autoincrement=True, index=True)
    user_id     = Column(String, nullable=False, index=True)
    delta       = Column(Integer, nullable=False)            # + grant, - debit
    balance_after = Column(Integer, nullable=True)           # balance immediately after this entry
    reason      = Column(String(64), nullable=False)         # 'pack_purchase' | 'report' | 'presales' | 'admin_grant' | 'refund'
    action      = Column(String(64), nullable=True)          # the billable action, when a debit
    ref_id      = Column(String, nullable=True, index=True)  # chat_history_id / pipeline_run_id / stripe session id
    created_at  = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))

class UserDocuments(Base):
    __tablename__ = "user_documents"
    document_id = Column(String, primary_key=True, nullable=False,index=True,default=new_id)
    user_id = Column(String, ForeignKey(User.user_id), nullable=False, index=True)
    document_path = Column(String, nullable=False)
    active_tag = Column(Boolean, nullable=False, default=text("True"))
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))

class ChatHistory(Base):
    __tablename__ = "chat_history"
    chat_history_id = Column(String, primary_key=True, nullable=False, index=True, default=new_id)
    user_id = Column(String,ForeignKey(User.user_id), nullable=False,index=True)
    document_id = Column(String, ForeignKey(UserDocuments.document_id), nullable=False, index=True)
    # active_tag is UX-only: hides archived chats from the list view.
    # It does NOT affect billing — check_chat_limit counts chats by created_at
    # within the billing period (utils/subscription.py). Any future "restore"
    # endpoint that flips this to True must NOT also re-grant a billing slot.
    active_tag = Column(Boolean, nullable=False, default=text("True"))
    title = Column(String, nullable=True)
    # Firm-set display name for the project card. The LLM-generated `title` stays as
    # the searchable fallback; the card shows custom_title when present.
    custom_title = Column(String(200), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))
    modified_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))
    message = Column(String, nullable=False)
    message_count = Column(Integer, nullable=False, server_default=text("0"))


class SelectedChat(Base):
    __tablename__ = "selected_chat"
    selected_chat_id = Column(String, primary_key=True, nullable=False, index=True, default=new_id)
    chat_history_id = Column(String, ForeignKey(ChatHistory.chat_history_id), nullable=False, index=True)
    document_id = Column(String, ForeignKey(UserDocuments.document_id), nullable=False, index=True)
    user_id = Column(String, ForeignKey(User.user_id), nullable=False, index=True)
    title = Column(String, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))
    modified_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))
    message = Column(String, nullable=False)

class ReportVersions(Base):
    __tablename__ = "report_version"
    report_version_id = Column(String, primary_key=True, nullable=False, index=True, default=new_id)
    chat_history_id = Column(String, ForeignKey(ChatHistory.chat_history_id), nullable=False, index=True)
    user_id = Column(String, ForeignKey(User.user_id), nullable=False, index=True)
    version_number = Column(Integer, nullable=False, default=1, index=True)
    report_content = Column(String, nullable=False)
    summary_report = Column(JSON, nullable=False)
    pending_changes = Column(JSON, nullable=True, default=[])  # Track modifications before regeneration
    report_contract = Column(JSON, nullable=True, default=None)  # Structured ReportContract (contract pipeline); NULL for legacy runs
    schema_version = Column(String, nullable=False, default="1.0")  # For future migrations
    is_default = Column(Boolean, nullable=False, default=True, index=True)  # Mark as default/recommended version
    # Changelog tracking fields
    changes_applied = Column(JSON, nullable=True, default=None)  # Pending changes that created this version
    changelog_summary = Column(Text, nullable=True)  # LLM-generated summary of what changed and why
    parent_version_id = Column(String, nullable=True)  # Reference to the version this was based on
    is_client_signoff = Column(Boolean, nullable=False, default=False, index=True)  # The version the client signed off on (the change-order baseline). One per project.
    signoff_at = Column(TIMESTAMP(timezone=True), nullable=True, default=None)  # When it was pinned as the baseline
    pre_mortem = Column(JSON, nullable=True, default=None)  # Adversarial-persona objections (A6) — NULL until generated
    deliverable_config = Column(JSON, nullable=True, default=None)  # Deliverable Builder (A5) curation state
    deliverable_polished_sections = Column(JSON, nullable=True, default=None)  # Per-section LLM polish overrides
    deliverable_updated_at = Column(TIMESTAMP(timezone=True), nullable=True, default=None)
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
                         default=new_id)
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

    # Opaque token for the public client questionnaire (WS-3). NULL = no link issued;
    # set when the BA shares, nulled to revoke. The token alone authorizes read +
    # answer-submit on the public endpoints (no login).
    client_share_token = Column(String(64), nullable=True, unique=True, index=True)
    # Client portal (WS-3 v2): recipient email (set on first send, reused for reminders)
    # and the submit signal (set when the client clicks "Submit to firm" → firm reviews).
    client_email = Column(String(320), nullable=True)
    client_submitted_at = Column(TIMESTAMP(timezone=True), nullable=True)
    # Who actually completed the questionnaire (captured at submit, for the firm's
    # record/proof of submission): {"name", "designation", "email"}.
    client_respondent = Column(JSON, nullable=True)
    # When the questionnaire link was shared with the client (email send OR the firm
    # marking it manually sent). Drives the dashboard "sent" status.
    client_link_shared_at = Column(TIMESTAMP(timezone=True), nullable=True)
    # Durable lifetime counter of public "Check readiness" LLM calls on this link —
    # the hard ceiling that caps LLM cost per token even if Redis (the windowed
    # throttle) is down. Never fails open.
    client_check_count = Column(Integer, nullable=False, server_default=text("0"), default=0)

    # Metadata
    status = Column(String(50), nullable=False, default=PresalesStatus.PROCESSING)
    model_used = Column(String(100), nullable=True)       # e.g., "gpt-4o-mini"
    processing_time_seconds = Column(Integer, nullable=True)

    # Materialized COGS roll-up across this presales project (scan + brief + chat) —
    # SUM(llm_call_log.cost_usd) / COUNT where llm_call_log.presales_id == this id.
    total_cost_usd = Column(Float, nullable=False, server_default=text("0"), default=0.0)
    total_calls = Column(Integer, nullable=False, server_default=text("0"), default=0)

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
                     default=new_id)
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
                     default=new_id)
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
    FOLLOW_UP = "follow_up"       # Generated by the answer analyzer from the user's answers


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
                         default=new_id)
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
                        default=new_id)
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
                                  default=new_id)
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


class PipelineRunStatus:
    """Lifecycle states for a 9-agent full pipeline run."""
    QUEUED    = "queued"
    RUNNING   = "running"
    COMPLETED = "completed"
    FAILED    = "failed"
    CANCELLED = "cancelled"


class PipelineRun(Base):
    """
    Tracks one asynchronous execution of the 9-agent full pipeline.

    Created when the user clicks "Open Chat" on the presales report. The
    background task updates this row as each LangGraph node executes so the
    frontend can poll /full-pipeline/status/{chat_history_id} and render
    per-stage progress. UNIQUE(chat_history_id) enforces a single in-flight
    run per project; restarts overwrite the row.
    """
    __tablename__ = "pipeline_runs"

    run_id           = Column(String, primary_key=True, nullable=False, index=True,
                              default=new_id)
    chat_history_id  = Column(String, ForeignKey(ChatHistory.chat_history_id),
                              nullable=False, unique=True, index=True)
    user_id          = Column(String, ForeignKey(User.user_id), nullable=False, index=True)

    status           = Column(String(20), nullable=False, default=PipelineRunStatus.QUEUED, index=True)
    current_stage    = Column(String(64), nullable=True)
    stages_completed = Column(JSON, nullable=False, default=list)
    loop_count       = Column(Integer, nullable=False, default=0)
    error            = Column(Text, nullable=True)

    started_at       = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))
    completed_at     = Column(TIMESTAMP(timezone=True), nullable=True)

    # Bet 2.C — resumable pipeline. NULL on legacy runs.
    state_snapshot      = Column(JSON, nullable=True)
    last_completed_node = Column(String(64), nullable=True)

    # Materialized COGS roll-up — SUM(llm_call_log.cost_usd) / COUNT for this run,
    # frozen on completion so billing reads don't re-aggregate and stay correct even
    # if pricing changes later. Per-call detail lives in llm_call_log.
    total_cost_usd      = Column(Float, nullable=False, server_default=text("0"), default=0.0)
    total_calls         = Column(Integer, nullable=False, server_default=text("0"), default=0)


class TransactionHistory(Base):
    """
    Tracks all reversible actions for undo/redo functionality.

    Each transaction stores enough data to reverse the action.
    The undo/redo stacks are managed per chat session.
    """
    __tablename__ = "transaction_history"

    id = Column(String, primary_key=True, nullable=False, index=True,
                default=new_id)
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


class LLMCallLog(Base):
    """
    Per-call LLM telemetry. One row per ChatOpenAI invocation across the
    agentic / presales pipelines and the chat paths. Powers /admin/llm-stats
    and the prompt-caching before/after comparison (see migration 013).

    cached_input_tokens is the OpenAI prompt-cache hit subset and is billed
    at the discounted cached rate by utils.llm_pricing.compute_cost.
    """
    __tablename__ = "llm_call_log"

    id                  = Column(Integer, primary_key=True, autoincrement=True, index=True)
    # Scope ids are LOGICAL references, NOT hard FKs. A cost/telemetry ledger must
    # tolerate out-of-order writes (a call recorded before its parent row is saved —
    # e.g. the initial presales scan) and must OUTLIVE the business rows it references
    # (we still need the cost record for billing after a project/presales is deleted).
    # A hard FK here silently dropped every initial-scan call on insert. Keep indexed.
    chat_history_id     = Column(String, nullable=True, index=True)
    pipeline_run_id     = Column(String, nullable=True, index=True)
    presales_id         = Column(String, nullable=True, index=True)
    user_id             = Column(String, nullable=True, index=True)

    agent_name          = Column(String(64), nullable=False, index=True)
    model               = Column(String(64), nullable=False)

    prompt_hash         = Column(String(64), nullable=True, index=True)

    input_tokens        = Column(Integer, nullable=False, default=0)
    cached_input_tokens = Column(Integer, nullable=False, default=0)
    output_tokens       = Column(Integer, nullable=False, default=0)
    latency_ms          = Column(Integer, nullable=False, default=0)
    cost_usd            = Column(Float, nullable=False, default=0.0)

    created_at          = Column(TIMESTAMP(timezone=True), nullable=False,
                                 server_default=text("now()"))


class ModelPricing(Base):
    """Per-1M-token price book — the source of truth for COGS once seeded.

    Mirrors utils.llm_pricing.SEED_PRICES into the DB so rates can be updated
    without a deploy and refreshed by the daily LiteLLM-diff job. `model` is the
    canonical family key (e.g. 'gpt-4o'); concrete dated snapshots are normalized
    to it at lookup time. The in-code SEED_PRICES remains the bootstrap + the
    last-resort fallback, so pricing never hard-depends on the DB being populated.
    """
    __tablename__ = "model_pricing"

    model               = Column(String(64), primary_key=True, nullable=False, index=True)
    provider            = Column(String(32), nullable=True)
    input_per_1m        = Column(Float, nullable=False, default=0.0)
    cached_input_per_1m = Column(Float, nullable=False, default=0.0)
    output_per_1m       = Column(Float, nullable=False, default=0.0)
    source              = Column(String(255), nullable=True)   # 'seed' | 'manual' | 'litellm:<date>'
    effective_date      = Column(TIMESTAMP(timezone=True), nullable=True)
    updated_at          = Column(TIMESTAMP(timezone=True), nullable=False,
                                 server_default=text("now()"), onupdate=text("now()"))


# ============================================================================
# FIRM CONTEXT MODELS (Bet 3 - migration 019)
# ============================================================================

class Firm(Base):
    """A consultancy/firm. Tenant boundary for rate cards, templates, past projects."""
    __tablename__ = "firms"

    firm_id        = Column(String, primary_key=True, nullable=False, index=True,
                            default=lambda: new_hex("firm_"))
    name           = Column(String(255), nullable=False)
    logo_url       = Column(Text, nullable=True)
    primary_color  = Column(String(7), nullable=True)  # '#RRGGBB' for Bet 4 branded exports
    # Per-org overrides for client email copy, edited by staff in the admin console.
    # Shape: {"questionnaire_invite": {subject, heading, intro, button_label, signoff}, "questionnaire_reminder": {...}}.
    # GroundedIQ branding + the email shell are NEVER overridable — only the text fields.
    email_templates = Column(JSON, nullable=True)
    created_at     = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))
    updated_at     = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"),
                            onupdate=text("now()"))


class FirmRateCard(Base):
    __tablename__ = "firm_rate_cards"

    rate_id          = Column(String, primary_key=True, nullable=False, index=True,
                              default=new_id)
    firm_id          = Column(String, ForeignKey(Firm.firm_id, ondelete="CASCADE"),
                              nullable=False, index=True)
    role             = Column(String(64), nullable=False)
    seniority        = Column(String(32), nullable=False)
    region           = Column(String(32), nullable=False)
    hourly_rate_usd  = Column(Float, nullable=False)
    version          = Column(Integer, nullable=False, default=1)
    active           = Column(Boolean, nullable=False, default=True)
    created_at       = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))


class FirmTeamTemplate(Base):
    __tablename__ = "firm_team_templates"

    template_id     = Column(String, primary_key=True, nullable=False, index=True,
                             default=new_id)
    firm_id         = Column(String, ForeignKey(Firm.firm_id, ondelete="CASCADE"),
                             nullable=False, index=True)
    template_name   = Column(String(128), nullable=False)
    engagement_type = Column(String(64), nullable=True)
    roles           = Column(JSON, nullable=False)   # [{role, seniority, count, allocation_pct}]
    notes           = Column(Text, nullable=True)
    active          = Column(Boolean, nullable=False, default=True)
    created_at      = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))


class FirmTechPreference(Base):
    __tablename__ = "firm_tech_preferences"

    pref_id        = Column(String, primary_key=True, nullable=False, index=True,
                            default=new_id)
    firm_id        = Column(String, ForeignKey(Firm.firm_id, ondelete="CASCADE"),
                            nullable=False, index=True)
    category       = Column(String(64), nullable=False)
    preferred      = Column(JSON, nullable=False)         # ['AWS', 'GCP']
    anti_preferred = Column(JSON, nullable=True)          # ['Azure']
    rationale      = Column(Text, nullable=True)
    created_at     = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))


class FirmPastProject(Base):
    __tablename__ = "firm_past_projects"

    project_id              = Column(String, primary_key=True, nullable=False, index=True,
                                     default=new_id)
    firm_id                 = Column(String, ForeignKey(Firm.firm_id, ondelete="CASCADE"),
                                     nullable=False, index=True)
    project_name            = Column(String(255), nullable=False)
    client_name             = Column(String(255), nullable=True)
    engagement_type         = Column(String(64), nullable=True)
    start_date              = Column(DateTime(timezone=True), nullable=True)
    end_date                = Column(DateTime(timezone=True), nullable=True)
    summary                 = Column(Text, nullable=True)
    original_brief_md       = Column(Text, nullable=True)
    final_report_md         = Column(Text, nullable=True)
    retrospective_md        = Column(Text, nullable=True)
    effort_estimated_weeks  = Column(Float, nullable=True)
    effort_actual_weeks     = Column(Float, nullable=True)
    created_at              = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))


# ---------------------------------------------------------------------------
# Operational control plane (migration 0010) — dynamic, no-restart site config.
# Durable in Postgres (Redis here is non-persistent, so it can't be the source
# of truth for "are we in maintenance"). Read via utils.ops_state.get_ops_state()
# behind a short TTL cache; admin writes call ops_state.invalidate().
# ---------------------------------------------------------------------------
class SiteSetting(Base):
    """Key/value operational config so a new flag needs no migration. Seeded keys:
      - 'maintenance'    {on, title, message, eta, allowlist_ips[], allowlist_emails[]}
      - 'read_only'      {on, message}
      - 'feature_flags'  {signups_enabled, logins_enabled, pipeline_enabled}
    """
    __tablename__ = "site_settings"
    key        = Column(String(64), primary_key=True)
    value      = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"), onupdate=func.now())
    updated_by = Column(String, nullable=True)


class Announcement(Base):
    """User-facing banner shown by the SPA via GET /site-config. Time-windowed +
    dismissible. `kind` drives the colour; `audience` is 'all' | 'authenticated' | 'users'."""
    __tablename__ = "announcements"
    id          = Column(String, primary_key=True, default=new_id)
    kind        = Column(String(20), nullable=False, server_default=text("'info'"))  # info|warning|outage|maintenance|success
    title       = Column(String(200), nullable=False)
    body        = Column(Text, nullable=True)
    active      = Column(Boolean, nullable=False, server_default=text("true"))
    starts_at   = Column(TIMESTAMP(timezone=True), nullable=True)
    ends_at     = Column(TIMESTAMP(timezone=True), nullable=True)
    dismissible = Column(Boolean, nullable=False, server_default=text("true"))
    audience    = Column(String(20), nullable=False, server_default=text("'all'"))  # all|authenticated|users
    link_url    = Column(String(500), nullable=True)
    link_label  = Column(String(80), nullable=True)
    # When audience='users', the explicit recipient emails (lowercased list). Served ONLY
    # via the authenticated /my-site-config endpoint (matched server-side against the
    # caller's email) — never the public /site-config — so the recipient list is never
    # exposed to anonymous clients.
    target_emails = Column(JSONB, nullable=True)
    created_at  = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))
    updated_at  = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"), onupdate=func.now())
    created_by  = Column(String, nullable=True)


class ChangelogEntry(Base):
    """Product 'what's new' feed. Only `published` entries surface in the app."""
    __tablename__ = "changelog_entries"
    id           = Column(String, primary_key=True, default=new_id)
    version      = Column(String(40), nullable=True)
    title        = Column(String(200), nullable=False)
    body         = Column(Text, nullable=True)
    category     = Column(String(20), nullable=True)  # feature|fix|improvement
    media_url    = Column(String(500), nullable=True)  # optional GIF/image URL shown in "What's new"
    published    = Column(Boolean, nullable=False, server_default=text("false"))
    published_at = Column(TIMESTAMP(timezone=True), nullable=True)
    created_at   = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))
    updated_at   = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"), onupdate=func.now())
    created_by   = Column(String, nullable=True)


class SupportTicket(Base):
    """In-app Help & Support submission (bug report / feedback / question), and the
    head of an email-driven conversation. The original message is stored here; later
    replies (user→inbound via the Resend webhook, staff→outbound via the admin panel)
    live in `SupportMessage`. `ref_code` is the human-friendly id shown to the user
    and embedded in every outbound subject so inbound replies thread back here.
    `user_id` is nullable: an inbound email from a non-user still opens a ticket."""
    __tablename__ = "support_tickets"
    ticket_id       = Column(String, primary_key=True, default=new_id, index=True)
    ref_code        = Column(String(16), nullable=False, index=True)   # e.g. "GIQ-A1B2C3"
    user_id         = Column(String, ForeignKey(User.user_id), nullable=True, index=True)
    requester_email = Column(String, nullable=True, index=True)        # who we reply to
    category        = Column(String(24), nullable=False)               # bug|idea|question|billing
    subject         = Column(String(200), nullable=False)
    message         = Column(Text, nullable=False)
    screenshot_path = Column(String, nullable=True)                    # S3 key(s), comma-separated; optional
    status          = Column(String(16), nullable=False, server_default=text("'open'"))  # open|resolved
    created_at      = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))
    updated_at      = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"), onupdate=func.now())


class SupportMessage(Base):
    """One message in a support ticket's conversation. `direction='inbound'` is a
    reply from the requester (ingested from the Resend inbound webhook);
    `direction='outbound'` is a staff reply sent from the admin panel via Resend.
    `provider_message_id` carries the Resend `email_id` for inbound dedupe."""
    __tablename__ = "support_messages"
    message_id          = Column(String, primary_key=True, default=new_id, index=True)
    ticket_id           = Column(String, ForeignKey("support_tickets.ticket_id"), nullable=False, index=True)
    direction           = Column(String(10), nullable=False)           # inbound | outbound
    author_email        = Column(String, nullable=True)
    author_name         = Column(String, nullable=True)
    body                = Column(Text, nullable=False, server_default=text("''"))
    body_html           = Column(Text, nullable=True)
    attachments         = Column(JSON, nullable=True)                  # [{filename, key?}]
    provider_message_id = Column(String, nullable=True, index=True)    # Resend email_id (inbound) — dedupe key
    created_at          = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))