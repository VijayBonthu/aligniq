from fastapi import  Depends, APIRouter, HTTPException,Request,Header
from fastapi.responses import FileResponse
from utils.token_generation import token_validator, validate_token_incoming_requests
from sqlalchemy.orm import Session
from models import get_db
from utils.integrations import Integrations
from utils.logger import logger
import os

router = APIRouter()

@router.get("/jira/get_issues")
async def get_jira_issues(current_user = Depends(token_validator), db:Session=Depends(get_db)):
    
    
    if not current_user['jira_token']:
        raise HTTPException(status_code=401, detail="Jira authorization header is required")
    # payload = validate_token_incoming_requests(current_user['jira_token']['jira_access_token'])
    # logger.info(f"payload: {payload}")
    issues = Integrations(current_user['jira_token']['jira_access_token']).get_all_issues()
    return {"issues": issues}

@router.get("/jira/download_attachments")
async def download_jira_attachements(issue_key:str = None, current_user = Depends(token_validator), download_file_name:str = None, attachment_id=None):
    if not current_user['jira_token']:
        raise HTTPException(status_code=401, detail="Jira authorization header is required")  
    if not issue_key:
        raise HTTPException(status_code=400, detail="issue key is required")
    if not download_file_name:
        raise HTTPException(status_code=400, detail="download file name is required")
    if not attachment_id:
        raise HTTPException(status_code=400, detail="attachment id is required")
    issues = Integrations(current_user['jira_token']['jira_access_token']).download_jira_attachments(issue_key=issue_key, download_file_name=download_file_name, attachment_id=attachment_id)
    if not issues or len(issues) == 0:
        raise HTTPException(status_code=404, detail="Attachment not found")
    
    file_info = issues[0]
    file_path = file_info['local_path']

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Attachment file not found")
    content_type = "application/octet-stream"
    if download_file_name.lower().endswith('.pdf'):
        content_type = "application/pdf"
    elif download_file_name.lower().endswith('.docx'):
        content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    elif download_file_name.lower().endswith('.doc'):
        content_type = "application/msword"
    elif download_file_name.lower().endswith('.txt'):
        content_type = "text/plain"
    
    return FileResponse(
        path=file_path,
        filename=download_file_name,
        media_type=content_type
    )
    # return {"issues": issues}

@router.get('/jira/get_single_issue/{issue_key}')
async def get_single_issue(issue_key:str = None, current_user = Depends(token_validator)):
    print(f"current_user_details {current_user}")
    print(issue_key)
    if not current_user['jira_token']:
        raise HTTPException(status_code=401, detail="Jira authorization header is required")
    if not issue_key:
        raise HTTPException(status_code=400, detail="issue key is required")
    issues = Integrations(current_user['jira_token']['jira_access_token']).get_single_issues_(issue_key=issue_key)
     
    return {"issues": issues}
