from __future__ import annotations

from sqlalchemy.orm import Session
from typing import Dict, List
import models
import json
from sqlalchemy import text, and_
import uuid
from fastapi import HTTPException
from utils.logger import logger

async def save_chat_history(chat:Dict, db:Session) -> Dict:
    """
    Save or update chat history

    Args:
    {
        chat_history_id: str,
        user_id: str,
        document_id: str,
        message: [{role:str, content:str}],
        title: str,
        active_tag: bool,
    }
    db:Database session

    Returns:
    Dict: Saved chat history details
    """


    try:
        #convert message object to json
        message_json = json.dumps(chat["message"])

        if "chat_history_id" in chat and chat["chat_history_id"] and chat["chat_history_id"] != "":
            #Get Existing record
            logger.info(f"getting the chat details to save for existing user in chat history table: {chat['user_id']}")
            chat_record = db.query(models.ChatHistory)\
            .filter(models.ChatHistory.chat_history_id == chat["chat_history_id"])\
            .first()
            if not chat_record:
                raise HTTPException(status_code=404, detail="Chat history not found")
            logger.info(f"updating the chat details for user: {chat['user_id']}")
            chat_record.message = message_json
            if "title" in chat:
                chat_record.title = chat["title"]
            chat_record.modified_at = text("now()")
            db.commit()
            logger.info(f"commit done: {chat['user_id']}")
            db.refresh(chat_record)
            logger.info(f"chat details saved for user: {chat['user_id']}")
            return {
                "chat_history_id": chat_record.chat_history_id,
                "user_id": chat_record.user_id,
                "document_id": chat_record.document_id,
                "message": chat["message"],
                "title": chat_record.title,
                "modified_at": str(chat_record.modified_at),
                "status": "updated"
            }
        else:
            # Check if chat already exists for this user_id + document_id
            logger.info(f"checking if chat already exists for user_id: {chat['user_id']}, document_id: {chat['document_id']}")
            existing_chat = db.query(models.ChatHistory)\
                .filter(and_(
                    models.ChatHistory.user_id == chat["user_id"],
                    models.ChatHistory.document_id == chat["document_id"],
                    models.ChatHistory.active_tag == True
                ))\
                .order_by(models.ChatHistory.created_at.desc())\
                .first()

            if existing_chat:
                # Update existing chat instead of creating duplicate
                logger.info(f"found existing chat_history_id: {existing_chat.chat_history_id}, updating instead of creating new")
                existing_chat.message = message_json
                if "title" in chat:
                    existing_chat.title = chat["title"]
                existing_chat.modified_at = text("now()")
                db.commit()
                db.refresh(existing_chat)
                logger.info(f"updated existing chat for user: {chat['user_id']}")
                return {
                    "chat_history_id": existing_chat.chat_history_id,
                    "user_id": existing_chat.user_id,
                    "document_id": existing_chat.document_id,
                    "message": chat["message"],
                    "title": existing_chat.title,
                    "modified_at": str(existing_chat.modified_at),
                    "status": "updated"
                }
            else:
                # Create new chat only if none exists
                logger.info(f"no existing chat found, creating new chat for user: {chat['user_id']}")
                chat_history_id = str(uuid.uuid4())
                new_chat = models.ChatHistory(
                    chat_history_id = chat_history_id,
                    user_id = chat["user_id"],
                    document_id = chat["document_id"],
                    message = message_json,
                    title = chat["title"],
                )
                logger.info(f"adding the chat details for new user in chat history table: {chat['user_id']}")
                db.add(new_chat)
                db.commit()
                db.refresh(new_chat)
                return {
                    "chat_history_id": new_chat.chat_history_id,
                    "user_id": new_chat.user_id,
                    "document_id": new_chat.document_id,
                    "message": chat["message"],
                    "title": new_chat.title,
                    "status": "created"
                }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
    

async def delete_chat_history(user_id:str, chat_history_id:str, db:Session):
    """
    mark the chat history active tag to False

    Args:
    user_id: str,
    chat_history_id: str,
    active_tag: bool,

    Returns:
    Dict: marks the chat history active tag to False
    """
    try:
        chat_history_id = chat_history_id.strip('"\'')
        logger.info(f"details received for deleting the chat history for user: {user_id}, chat_history_id: {chat_history_id}")
        user_details = db.query(models.ChatHistory)\
        .filter(and_(models.ChatHistory.user_id == user_id, models.ChatHistory.chat_history_id == chat_history_id, models.ChatHistory.active_tag == "True")).first()
        logger.info(f"user_details: {user_details}")
        if not user_details:
            raise HTTPException(status_code=404, detail="Chat history not found")
        user_details.active_tag = False
        user_details.modified_at = text("now()")
        db.commit()
        db.refresh(user_details)
        return {
            "chat_history_id": user_details.chat_history_id,
            "user_id": user_details.user_id,
            "status":"deleted"
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Internal server error")
    
async def get_user_chat_history_details(user_id:str, db:Session):
    try:
        user_chat_details = db.query(models.ChatHistory).filter(and_(models.ChatHistory.user_id == user_id, models.ChatHistory.active_tag == "True")).all()
        if user_chat_details:
            full_chat_history = []
            for details in user_chat_details:
                full_history = {}
                full_history["document_id"] = details.document_id
                full_history["chat_history_id"] = details.chat_history_id
                full_history["title"] = details.title
                full_history["modified_at"] = details.modified_at
                full_chat_history.append(full_history)
            return full_chat_history
        else:
            raise HTTPException(status_code=404, detail=f"Chat history not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error")

async def get_single_user_chat_history(user_id:str, chat_history_id:str, db:Session):
    try:
        user_chat_details = db.query(models.ChatHistory).filter(and_(models.ChatHistory.user_id == user_id, models.ChatHistory.active_tag == "True", models.ChatHistory.chat_history_id == chat_history_id)).first()
        if user_chat_details:
            full_history = {}
            full_history["chat_history_id"] = user_chat_details.chat_history_id
            full_history["document_id"] = user_chat_details.document_id
            full_history["title"] = user_chat_details.title
            full_history["modified_at"] = user_chat_details.modified_at
            full_history["message"] = user_chat_details.message
            return full_history
        else:
            raise HTTPException(status_code=404, detail="Chat history not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error")
    
async def save_chat_with_doc(chat_context:Dict, db:Session):
    """
    saves the selected chat to continue the conversation

    Args: chat_context: Dict,
    db: Session

    Returns: Dict: saved chat details

    """
    try:
        chat_details = db.query(models.SelectedChat).filter(models.SelectedChat.chat_history_id == chat_context["chat_history_id"]).first()
        if chat_details:
            chat_details.message = json.dumps(chat_context["message"])
            chat_details.modified_at = text("now()")
            chat_details.title = chat_context["title"]
            db.commit()
        else:
            logger.info(f"Hitting in else block")
            chat_context["message"] = json.dumps(chat_context["message"])
            content = models.SelectedChat(**chat_context)
            logger.info(f"content: {content}")
            db.add(content)
            db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Error in saving the selected chat: {str(e)}")

async def save_report_version(summary_report_details:Dict, db:Session):
    """
    save_report_version
    
    :param summary_report_details: Description
    :type summary_report_details: Dict
    :param db: Description
    :type db: Session


    """
    try:
        report_details_exists = db.query(models.ReportVersions).filter(models.ReportVersions.chat_history_id == summary_report_details["chat_history_id"]).order_by(models.ReportVersions.created_at.desc()).first()
        if report_details_exists:
            version_details = report_details_exists.version_number + 1

            new_report_insert = models.ReportVersions(
                report_version_id = str(uuid.uuid4()),
                chat_history_id = summary_report_details["chat_history_id"],
                user_id = summary_report_details["user_id"],
                version_number = version_details,
                report_content = summary_report_details["report_content"],
                summary_report = summary_report_details["summary_report"]
            )
            db.add(new_report_insert)
            db.commit()
            db.refresh(new_report_insert)
            logger.info(f"new report version saved successfully for chat_history_id: {str(summary_report_details['chat_history_id'])} and version: {str(version_details)} for user: {str(summary_report_details['user_id'])}")
        else:
            new_report_insert = models.ReportVersions(
                report_version_id = str(uuid.uuid4()),
                chat_history_id = summary_report_details["chat_history_id"],
                user_id = summary_report_details["user_id"],
                report_content = summary_report_details["report_content"],
                summary_report = summary_report_details["summary_report"]
            )
            db.add(new_report_insert)
            db.commit()
            db.refresh(new_report_insert)
            logger.info(f"brand new report version saved successfully for chat_history_id: {str(summary_report_details['chat_history_id'])} for user: {str(summary_report_details['user_id'])}")
    except Exception as e:
        db.rollback()
        logger.error(f"Error in saving the report version: {str(e)}")



        
    
