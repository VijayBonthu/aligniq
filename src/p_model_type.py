
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, UUID4, ConfigDict
from datetime import datetime

class UploadDoc(BaseModel):
    expected_time:str = None
    list_of_developers:Optional[list[str]] = None

class Registration_login(BaseModel):
    email:str
    id:str = None
    given_name:str
    family_name:str
    verified_email:bool=False
    name:str
    picture:str = None
    provider:str = None

class Registration_login_password(BaseModel):
    email:str
    given_name:str
    family_name:str
    password:str
    username: Optional[str] = None
    role: Optional[str] = None

class login_details(BaseModel):
    email_address:str
    password:str

class JiraTokenRequest(BaseModel):
    jira_access_token:str

class MessageContent(BaseModel):
    role: str
    content: str
    timestamp: Optional[str] = None
    selected: Optional[bool] = True  # Default to True for backward compatibility
    type: Optional[str] = None  # Message type: "hybrid_response", "suggestion_confirmed", etc.
    pending_suggestion: Optional[Dict[str, Any]] = None  # For hybrid flow: stores awaiting confirmation

    model_config = ConfigDict(extra="allow")  # Allow extra fields to pass through without stripping

class ChatHistoryDetails(BaseModel):
    chat_history_id:Optional[str] = None
    user_id:str
    document_id:str
    message:List[MessageContent]
    title:Optional[str] = None

class SessionResponse(BaseModel):
    id: UUID4
    user_id: UUID4
    status: str
    document_name: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]
    
    class Config:
        from_attributes = True
