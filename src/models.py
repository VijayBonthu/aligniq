from sqlalchemy import Column, String, Integer, create_engine, ForeignKey, Boolean
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
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = Column(TIMESTAMP(timezone=True), nullable=True, onupdate=text("now()"))


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
    technology_risks = Column(JSON, nullable=True)        # Tech risks identified by LLM
    kickstart_questions = Column(JSON, nullable=True)     # Critical questions for client

    # Final brief (markdown)
    presales_brief = Column(Text, nullable=True)

    # Metadata
    status = Column(String(50), nullable=False, default=PresalesStatus.PROCESSING)
    model_used = Column(String(100), nullable=True)       # e.g., "gpt-4o-mini"
    processing_time_seconds = Column(Integer, nullable=True)

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