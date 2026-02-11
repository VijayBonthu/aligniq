from fastapi import File, UploadFile, Form, Depends, APIRouter, HTTPException, status, Request, Security, BackgroundTasks, Body
from fastapi.responses import HTMLResponse
from typing import Optional
import os
import json
from utils.token_generation import token_validator
from utils.chat_history import save_chat_history, delete_chat_history, get_user_chat_history_details,get_single_user_chat_history, save_chat_with_doc, save_report_version
from getdata import ExtractText
from processdata import AccessLLM
from config import settings
from sqlalchemy.orm import Session
from models import get_db, UserDocuments
from database_scripts import user_documents, get_summary_report
from agents.workflow import ProjectScopingAgent
from utils.logger import logger
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jira_logic.jira_components import get_jira_user_info
from p_model_type import JiraTokenRequest, ChatHistoryDetails
import uuid
from datetime import datetime
from utils.document_save import get_s3_client,ensure_bucket_exists, upload_document_s3
from agents.workflow_graph import run_agent_pipeline
from agents import (
    PipelineError,
    PipelineTimeoutError,
    LLMTimeoutError,
    LLMRetryExhaustedError,
    AgentOutputError,
    AgentNotFoundError,
    # Pre-Sales Pipeline
    run_presales_pipeline,
    PresalesPipelineError,
    PresalesTimeoutError,
    PresalesAgentError
)
from agents.presales_workflow import generate_report_with_assumptions
import asyncio
from utils.helper_utils import save_file, upload_to_s3
from vectordb import vector_db, chunking
from utils.router_llm import (
    router_query_llm,
    conversation_summary_llm,
    count_token,
    generate_action_response,
    is_change_tracking_action,
    generate_change_acknowledgment,
    generate_conflict_resolution,
    generate_regeneration_plan
)
from database_scripts import (
    user_documents,
    get_summary_report,
    get_pending_changes,
    add_pending_change,
    clear_pending_changes,
    remove_pending_change,
    update_pending_change,
    detect_conflicts,
    get_pending_changes_summary,
    get_affected_sections,
    get_all_report_versions,
    get_report_version_by_number,
    create_new_report_version,
    rollback_to_version,
    get_report_diff,
    # Pre-Sales Database Functions
    save_presales_analysis,
    save_technology_risks,
    get_presales_analysis,
    get_presales_by_id,
    create_analysis_link,
    get_analysis_link,
    get_analysis_link_by_presales_id,
    update_analysis_link_with_full_report,
    save_user_answers,
    mark_risk_relevance,
    get_user_presales_history,
    # Question Management Functions
    create_presales_questions,
    get_presales_questions,
    update_question_answers,
    update_question_status,
    restore_question,
    update_presales_readiness,
    save_analysis_history,
    get_presales_with_questions,
    save_question_answer,
    # Undo/Rollback Functions
    get_last_pending_change,
    remove_last_pending_change
)
from agents.agentic_workflow import main_report_summary, regenerate_report_sections
import models


router = APIRouter()
# accessllm = AccessLLM(api_key=os.getenv("OPENAI_CHATGPT"))
UPLOADS_DIR = "uploads"
os.makedirs(UPLOADS_DIR, exist_ok=True) 

security = HTTPBearer()

# In-memory task storage (replace with database in production)
task_status = {}

async def process_document_task(file_path: str, user_id: str, document_id: str, task_id: str):
    try:
        # Initial steps remain the same until document extraction
        task_status[task_id] = {
            "status": "in_progress",
            "current_step": 0,
            "step_progress": 0,
            "message": "Reading document"
        }
        
        # Step 1: Extract text from document
        logger.info(f"file_path: {file_path}, user_id: {user_id}, document_id: {document_id}, task_id: {task_id}")
        task_status[task_id]["step_progress"] = 50
        document_data = await ExtractText(document_path=file_path, user_id=user_id, document_id=document_id).parse_document()
        task_status[task_id]["step_progress"] = 100
        logger.info(f"document_reading is complete")
        
        # Step 2: Process and combine document data
        
        task_status[task_id]["current_step"] = 1
        task_status[task_id]["step_progress"] = 0
        task_status[task_id]["message"] = "Processing content"
        logger.info(f"Processing the document started: {task_status[task_id]['message']}")
        
        full_data = []
        for i in range(len(document_data)):
            full_data.append(document_data[i]["data"])
        
        raw_requirements = "\n".join(
            str(item["data"]) if isinstance(item, dict) else str(item) for item in full_data
        )
        task_status[task_id]["step_progress"] = 100
        logger.info(f"Processing the document complete: {task_status[task_id]['message']}")
        
        # Step 3: Initialize ProjectScopingAgent and analyze requirements
        task_status[task_id]["current_step"] = 2
        task_status[task_id]["step_progress"] = 0
        task_status[task_id]["message"] = "Analyzing requirements"
        logger.info(f"Processing the analysing input started: {task_status[task_id]['message']}")
        raw_data = {
                "input": {
                    raw_requirements
                }
            }
        agent = ProjectScopingAgent()
        requirements = agent.analyze_input(raw_data["input"])
        task_status[task_id]["step_progress"] = 100
        logger.info(f"Processing the analysing input complete: {task_status[task_id]['message']}")
        
        # Step 4: Identify ambiguities 
        task_status[task_id]["current_step"] = 3 
        task_status[task_id]["step_progress"] = 0
        task_status[task_id]["message"] = "Identifying potential issues"
        logger.info(f"Processing the potential issues started: {task_status[task_id]['message']}")
        
        ambiguities = agent.identify_ambiguities()
        task_status[task_id]["step_progress"] = 100
        logger.info(f"Processing the potential issues complete: {task_status[task_id]['message']}")

        
        # Step 5: Generate tech recommendations
        task_status[task_id]["current_step"] = 4
        task_status[task_id]["step_progress"] = 0
        task_status[task_id]["message"] = "Generating technical recommendations"
        logger.info(f"Processing the tech recommendations started: {task_status[task_id]['message']}")
        
        tech_stack = agent.generate_tech_recommendations()
        task_status[task_id]["step_progress"] = 50
        
        # Generate PDF report
        pdf_filename = f"project_scoping_report_{document_id}.pdf"
        logger.info(f"final document is getting created: {pdf_filename}")
        agent.generate_pdf_report(pdf_filename)
        task_status[task_id]["step_progress"] = 100
        logger.info(f"Processing the tech recommendations started: {task_status[task_id]['message']}")
        
        # Set task as completed with comprehensive result
        task_status[task_id]["status"] = "completed"
        task_status[task_id]["result"] = {
            "summary": "Document processed successfully.",
            "document_id": document_id,
            "requirements": requirements,
            "ambiguities": ambiguities,
            "tech_stack": tech_stack,
            "pdf_report": pdf_filename,
            "chat_context": {
                "project_definition": requirements.get("project_definition", {}),
                "tech_recommendations": tech_stack.get("primary_stack", {}),
                "key_questions": ambiguities.get("questions", [])
            }
        }
        
        logger.info(f"Task {task_id} completed successfully")
        logger.info(f"task_status[task_id]['result']")
        
    except Exception as e:
        logger.error(f"Error processing document: {str(e)}")
        task_status[task_id]["status"] = "error"
        task_status[task_id]["message"] = str(e)


@router.post("/upload")
async def upload_file(
    background_tasks: BackgroundTasks,
    current_token: dict = Depends(token_validator),
    file: list[UploadFile] = File(...),
    analysis_mode: str = Form(default="presales"),  # "presales" (fast) or "full" (comprehensive)
    db: Session = Depends(get_db)
):
    """
    Upload document and run analysis.

    Args:
        file: Document file(s) to upload
        analysis_mode: Type of analysis to run
            - "presales": Fast pre-sales scan (60-120 sec) - DEFAULT
            - "full": Comprehensive analysis (5-10 min)

    Returns:
        For presales mode: Pre-sales brief with blockers, questions, risks
        For full mode: Comprehensive technical report
    """
    entire_doc_details = []
    for content_document in file:
        file_content = b''
        try:
            while chunk := await content_document.read(1024*1024):
                file_content += chunk
            logger.info(f"reading the file content")
            if len(file_content) > eval(settings.FILE_SIZE):
                raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File size exceed 10MB limit")
            logger.info("complete the file size check and reading < 50 MB")
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"file processing failed: {str(e)}")
        if not file_content:
            logger.warning(f"uploaded file is empty")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty")
        logger.info(f"completed reading the file")

        file_uuid = str(uuid.uuid4())
        file_extension = content_document.filename.split(".")[-1]
        document_name = content_document.filename.split(".")[0]
        user_dir = f"{UPLOADS_DIR}/{current_token['regular_login_token']['id']}"
        os.makedirs(user_dir, exist_ok=True) 
        

        file_path = os.path.join(f"{UPLOADS_DIR}/{current_token['regular_login_token']['id']}", f"{document_name}_{file_uuid}.{file_extension}")
        # try:
        #     with open(file_path, "wb") as f:
        #         f.write(file_content)
        #         logger.info(f"completed saving the file")
        # except Exception as e:
        #     raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"failed to save the file: {str(e)}")
        save_task = await save_file(file_path=file_path, file_content= file_content)
        
        # try:
        #     with open(file_path, 'rb') as file_obj:
        #         s3 = get_s3_client()
        #         response = ensure_bucket_exists(s3_client=s3, bucket_name= settings.S3_BUCKET_NAME)
        #         s3_file_path  = f"{UPLOADS_DIR}/{current_token['regular_login_token']['id']}/{document_name}_{file_uuid}.{file_extension}"
        #         logger.info(f"ensuring s3 is active with respose{response}")
        #         if response['bucket_status'] == 'exists':
        #             document_id = upload_document_s3(s3_client=s3, file_obj=file_obj, current_document_path=s3_file_path,content_type='application/pdf',bucket_name=settings.S3_BUCKET_NAME)
        # except HTTPException as e:
        #         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"failed to upload document to s3 since there is no bucket")

        upload_task = await upload_to_s3(file_path=file_path, file_extension=file_extension, file_uuid=file_uuid, document_name=document_name, current_token_id=current_token['regular_login_token']['id'], bucket_name= settings.S3_BUCKET_NAME, s3_folder=UPLOADS_DIR)

        # await asyncio.gather(save_task, upload_task)
        # logger.info(f"completed both saving and uploading the file to s3: {user_dir}")

        try:
            user_doc = {
                "user_id": current_token["regular_login_token"]["id"],
                "document_path": f"{UPLOADS_DIR}/{current_token['regular_login_token']['id']}/{document_name}_{file_uuid}.{file_extension}"
            }
            logger.info(f"user doc dict: {user_doc}")
            response = await user_documents(doc_data=user_doc, db=db)
            logger.info(f"completed the document upload")
            document_data = await ExtractText(document_path=response["document_path"],user_id=response["user_id"],document_id=response["document_id"]).parse_document()
            entire_doc_details.append(document_data)
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error occured please try again {str(e)}")
    logger.info(f"entire_doc_details: {entire_doc_details}")

    full_data = []
    for content_data in entire_doc_details:
        for i in range(len(content_data)):
            full_data.append(document_data[i]["data"])
        raw_requirements =  "\n".join(
                            str(item["data"]) if isinstance(item, dict) else str(item) for item in full_data
                                    )

    # Branch based on analysis mode
    user_id = current_token["regular_login_token"]["id"]
    document_id = response["document_id"]

    if analysis_mode == "presales":
        # Run fast pre-sales analysis (60-120 seconds)
        return await _run_presales_analysis(
            raw_requirements=raw_requirements,
            document_id=document_id,
            user_id=user_id,
            db=db
        )

    # Otherwise run full analysis pipeline
    logger.info(f"Starting full agent pipeline for document_id: {response['document_id']}")

    try:
        # Run the full agent pipeline
        result = await run_agent_pipeline(document=[raw_requirements])
        logger.info(f"Agent pipeline completed for document_id: {response['document_id']}")

        # Extract the final report from the pipeline result
        # The report is in state["message"][-1] as an AIMessage
        if not result.get("message") or len(result["message"]) == 0:
            logger.error(f"Pipeline returned empty message for document_id: {response['document_id']}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Report generation failed: No report was generated"
            )

        # Get the final report content (AIMessage.content)
        final_message = result["message"][-1]
        agent_response_message = final_message.content if hasattr(final_message, 'content') else str(final_message)

        # Extract title from requirements analyzer output
        document_title = "Technical Analysis Report"  # Default title
        try:
            req_analyzer_output = next(
                (item["output"] for item in result.get('req_analysis', [])
                 if item.get('agent') == 'requirements_analyzer'),
                None
            )
            if req_analyzer_output and isinstance(req_analyzer_output, dict):
                # Try to get title from project_definition or title field
                if "project_definition" in req_analyzer_output:
                    project_def = req_analyzer_output["project_definition"]
                    if isinstance(project_def, dict) and "title" in project_def:
                        document_title = project_def["title"]
                elif "title" in req_analyzer_output:
                    document_title = req_analyzer_output["title"]
        except Exception as title_error:
            logger.warning(f"Could not extract title from pipeline result: {str(title_error)}, using default")

        logger.info(f"Report generated with title: {document_title}")

        # Create initial chat history with assistant response
        initial_chat_data = {
            "user_id": current_token["regular_login_token"]["id"],
            "document_id": response["document_id"],
            "message": [
                {
                    "role": "assistant",
                    "content": agent_response_message,
                    "timestamp": datetime.now().isoformat(),
                    "selected": True  # Initial message is selected by default
                }
            ],
            "title": document_title
        }

        # Save to chat history and get chat_history_id
        logger.info(f"Saving initial chat history for document_id: {response['document_id']}")
        save_chat = await save_chat_history(chat=initial_chat_data, db=db)
        logger.info(f"Chat history created with chat_history_id: {save_chat['chat_history_id']}")

        if not save_chat:
            logger.error(f"Failed to save chat history for user: {current_token['regular_login_token']['id']} due to no response in save chat")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to save chat history")

        # Chunk the report for vector DB storage
        try:
            final_report_chunks = await chunking.chunk_text(text=agent_response_message)
            logger.info(f"Chunking complete for chat_history_id: {save_chat['chat_history_id']}, total chunks: {len(final_report_chunks)}")
        except Exception as e:
            logger.error(f"Error during chunking for chat_history_id: {save_chat['chat_history_id']}, error: {e}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Chunking failed: {e}")

        # Create embeddings and store in Chroma vector DB
        try:
            vectordb_resp = await vector_db.create_embeddings(
                texts=final_report_chunks,
                model=settings.EMBEDDING_MODEL,
                chat_history_id=save_chat["chat_history_id"]
            )
            logger.info(f"Successfully created embedding and added to vector DB for chat_history_id: {save_chat['chat_history_id']}")
        except Exception as e:
            logger.error(f"Error during embedding creation for chat_history_id: {save_chat['chat_history_id']}, error: {e}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Embedding creation failed: {e}")

        # Create summary of the report
        try:
            summary_report = await main_report_summary(main_report=agent_response_message)
            summary_detail_report = {
                "chat_history_id": save_chat["chat_history_id"],
                "user_id": save_chat["user_id"],
                "report_content": agent_response_message,
                "summary_report": summary_report
            }
            logger.info(f"Successfully created the summary report for chat_history_id: {save_chat['chat_history_id']}")

            # Save report version
            await save_report_version(summary_report_details=summary_detail_report, db=db)
            logger.info(f"Successfully saved the summary report for chat_history_id: {save_chat['chat_history_id']}")
        except Exception as e:
            logger.error(f"Error during summary report creation and saving for chat_history_id: {save_chat['chat_history_id']}, error: {str(e)}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error occurred on creating and saving the summary report: {str(e)}")

        # Return response with chat_history_id included
        return {
            "message": agent_response_message,
            "document_id": response["document_id"],
            "title": document_title,
            "chat_history_id": save_chat["chat_history_id"]
        }
    except PipelineTimeoutError as e:
        logger.error(f"Pipeline timeout for document_id: {response['document_id']}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=str(e)
        )

    except LLMTimeoutError as e:
        logger.error(f"LLM timeout for document_id: {response['document_id']}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"AI processing timed out. Please try again or use a shorter document."
        )

    except LLMRetryExhaustedError as e:
        logger.error(f"LLM retries exhausted for document_id: {response['document_id']}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI service temporarily unavailable. Please try again in a few minutes."
        )

    except (AgentOutputError, AgentNotFoundError) as e:
        logger.error(f"Agent error for document_id: {response['document_id']}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Report generation failed: {str(e)}"
        )

    except PipelineError as e:
        logger.error(f"Pipeline error for document_id: {response['document_id']}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Report generation failed: {str(e)}"
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Unexpected error during upload for document_id: {response.get('document_id', 'unknown')}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred during report generation. Please try again."
        )


# =============================================================================
# PRE-SALES WORKFLOW HELPER
# =============================================================================

async def _run_presales_analysis(
    raw_requirements: str,
    document_id: str,
    user_id: str,
    db: Session
) -> dict:
    """
    Run the fast pre-sales analysis pipeline (60-120 seconds).

    Args:
        raw_requirements: Extracted document text
        document_id: The document ID
        user_id: The user ID
        db: Database session

    Returns:
        dict with presales_brief, technology_risks, and metadata
    """
    logger.info(f"Starting pre-sales analysis for document_id: {document_id}")

    try:
        # Run the pre-sales pipeline
        result = await run_presales_pipeline(document=raw_requirements, timeout=180)

        if result.get("error"):
            logger.error(f"Pre-sales pipeline failed: {result['error']}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Pre-sales analysis failed: {result['error']}"
            )

        # Save pre-sales analysis to database
        presales_data = {
            "document_id": document_id,
            "user_id": user_id,
            "scanned_requirements": result.get("scanned_requirements"),
            "blind_spots": result.get("blind_spots"),
            "p1_blockers": result.get("p1_blockers", []),
            "technology_risks": result.get("technology_risks"),
            "kickstart_questions": result.get("critical_unknowns", []),
            "presales_brief": result.get("presales_brief"),
            "status": "completed",
            "model_used": settings.GENERATING_REPORT_MODEL,
            "processing_time_seconds": int(result.get("processing_times", {}).get("total", 0))
        }

        presales_record = await save_presales_analysis(presales_data=presales_data, db=db)
        presales_id = presales_record["presales_id"]
        logger.info(f"Saved pre-sales analysis with presales_id: {presales_id}")

        # Save technology risks for passive capture
        if result.get("technology_risks"):
            await save_technology_risks(
                risks=result["technology_risks"],
                presales_id=presales_id,
                document_id=document_id,
                user_id=user_id,
                model_used=settings.GENERATING_REPORT_MODEL,
                db=db
            )
            logger.info(f"Saved {len(result['technology_risks'])} technology risks")

        # Generate a meaningful title from the presales analysis
        scanned_reqs = result.get("scanned_requirements", {})
        project_summary = scanned_reqs.get("project_summary", "")
        # Extract first sentence or first 80 chars for title
        if project_summary:
            # Take first sentence or truncate
            first_sentence = project_summary.split('.')[0].strip()
            conversation_title = first_sentence[:80] + ('...' if len(first_sentence) > 80 else '')
        else:
            conversation_title = "Pre-Sales Analysis"

        # Create ChatHistory record so presales appears in conversation sidebar
        chat_data = {
            "user_id": user_id,
            "document_id": document_id,
            "message": [
                {
                    "role": "assistant",
                    "content": result.get("presales_brief", ""),
                    "timestamp": datetime.now().isoformat(),
                    "type": "presales_brief",
                    "presales_id": presales_id
                }
            ],
            "title": conversation_title
        }
        chat_record = await save_chat_history(chat=chat_data, db=db)
        chat_history_id = chat_record["chat_history_id"]
        logger.info(f"Created chat history for presales: {chat_history_id}")

        # Create analysis link with chat_history_id for unified tracking
        await create_analysis_link(
            document_id=document_id,
            user_id=user_id,
            presales_id=presales_id,
            chat_history_id=chat_history_id,
            db=db
        )
        logger.info(f"Created analysis link for presales_id: {presales_id} with chat_history_id: {chat_history_id}")

        # Create question records for tracking
        questions_result = await create_presales_questions(
            presales_id=presales_id,
            user_id=user_id,
            p1_blockers=result.get("p1_blockers", []),
            kickstart_questions=result.get("critical_unknowns", []),
            db=db
        )
        logger.info(f"Created {questions_result['total_count']} questions for presales_id: {presales_id}")

        # Build response compatible with frontend
        response_data = {
            # Frontend compatibility fields
            "message": result.get("presales_brief"),  # Frontend expects 'message'
            "document_id": document_id,
            "title": conversation_title,

            # Pre-sales specific fields
            "presales_id": presales_id,
            "analysis_mode": "presales",
            "presales_brief": result.get("presales_brief"),
            "scanned_requirements": result.get("scanned_requirements"),
            "blind_spots": result.get("blind_spots"),
            "p1_blockers": result.get("p1_blockers", []),
            "technology_risks": result.get("technology_risks"),
            "kickstart_questions": result.get("critical_unknowns", []),
            "processing_times": result.get("processing_times"),
            "status": "completed",

            # Chat history ID - allows presales to appear in conversation sidebar
            "chat_history_id": chat_history_id
        }

        logger.info(f"Pre-sales analysis completed. Brief length: {len(result.get('presales_brief', '') or '')} chars")
        return response_data

    except PresalesTimeoutError as e:
        logger.error(f"Pre-sales pipeline timed out: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Pre-sales analysis timed out. Please try again."
        )

    except PresalesAgentError as e:
        logger.error(f"Pre-sales agent error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Pre-sales analysis error: {str(e)}"
        )

    except PresalesPipelineError as e:
        logger.error(f"Pre-sales pipeline error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Pre-sales analysis failed: {str(e)}"
        )


# =============================================================================
# PRE-SALES API ENDPOINTS
# =============================================================================

@router.post("/generate-full-report/")
async def generate_full_report_from_presales(
    presales_id: str = Form(...),
    user_answers: Optional[str] = Form(default=None),  # JSON string of answers to kickstart questions
    assumptions: Optional[str] = Form(default=None),  # JSON string of assumptions from readiness analysis
    additional_context: Optional[str] = Form(default=None),  # Free-form additional context from user
    current_token: dict = Depends(token_validator),
    db: Session = Depends(get_db)
):
    """
    Generate a full comprehensive report from a pre-sales analysis.

    This endpoint triggers the full agent pipeline using the pre-sales
    analysis as context, along with any user-provided answers to kickstart questions.
    If assumptions are provided (from readiness analysis), the report will clearly
    distinguish between confirmed information and assumptions made.

    Args:
        presales_id: ID of the pre-sales analysis to build upon
        user_answers: JSON string of answers to kickstart questions
        assumptions: JSON string of assumptions list from readiness analysis
        additional_context: Free-form text with additional requirements, client notes, etc.

    Returns:
        Full technical report with chat_history_id
    """
    user_id = current_token["regular_login_token"]["id"]
    logger.info(f"Generating full report from presales_id: {presales_id}")

    try:
        # Get the pre-sales analysis
        presales = await get_presales_by_id(presales_id=presales_id, user_id=user_id, db=db)

        if not presales:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Pre-sales analysis not found: {presales_id}"
            )

        # Parse user answers if provided
        answers_dict = None
        if user_answers:
            try:
                answers_dict = json.loads(user_answers)
                # Save user answers
                await save_user_answers(
                    presales_id=presales_id,
                    user_answers=answers_dict,
                    db=db
                )
                logger.info(f"Saved user answers for presales_id: {presales_id}")
            except json.JSONDecodeError as e:
                logger.warning(f"Invalid user_answers JSON: {str(e)}")

        # Parse assumptions if provided
        assumptions_list = []
        if assumptions:
            try:
                assumptions_list = json.loads(assumptions)
                logger.info(f"Received {len(assumptions_list)} assumptions for report generation")
            except json.JSONDecodeError as e:
                logger.warning(f"Invalid assumptions JSON: {str(e)}")

        # Log additional context if provided
        if additional_context:
            logger.info(f"Received additional context ({len(additional_context)} chars) for report generation")

        # Get questions with answers
        questions = await get_presales_questions(presales_id, user_id, db)

        # Get the analysis link
        analysis_link = await get_analysis_link(
            document_id=presales["document_id"],
            user_id=user_id,
            db=db
        )

        # If we have assumptions, use the assumptions-aware report generator
        if assumptions_list:
            logger.info(f"Generating report with {len(assumptions_list)} assumptions")

            # Build document context
            document_context = json.dumps(presales.get('extracted_requirements', {}))

            # Generate report with assumptions
            result = await generate_report_with_assumptions(
                document=document_context,
                scanned_requirements=presales.get('extracted_requirements', {}),
                confirmed_answers=questions,
                assumptions_list=assumptions_list,
                additional_context=additional_context,
                timeout=180
            )

            if result.get("error"):
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Report generation failed: {result['error']}"
                )

            agent_response_message = result["report"]
            logger.info(f"Report with assumptions generated: {result['confirmed_count']} confirmed, {result['assumptions_count']} assumed")

        else:
            # No assumptions - use original pipeline
            # Build enhanced context from pre-sales output
            additional_context_section = ""
            if additional_context:
                additional_context_section = f"""
                                    ### Additional Context from Client/Team
                                    {additional_context}
                                    """

            enhanced_context = f"""
                                    ## Pre-Sales Analysis Context

                                    ### Project Summary
                                    {presales.get('extracted_requirements', {}).get('project_summary', 'N/A')}

                                    ### Technologies Identified
                                    {json.dumps(presales.get('extracted_requirements', {}).get('technologies_mentioned', []), indent=2)}

                                    ### Blind Spots & Risks Identified
                                    {json.dumps(presales.get('blind_spots', {}), indent=2)}

                                    ### User-Provided Answers to Kickstart Questions
                                    {json.dumps(answers_dict, indent=2) if answers_dict else 'No additional context provided'}
                                    {additional_context_section}
                                    ---

                                    ## Original Document Content
                                    (Note: Using pre-analyzed requirements for efficiency)
                                    """

            # Run the full agent pipeline with enhanced context
            result = await run_agent_pipeline(document=[enhanced_context])
            logger.info(f"Full agent pipeline completed for presales_id: {presales_id}")

            if not result.get("message") or len(result["message"]) == 0:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Report generation failed: No report was generated"
                )

            # Get the final report content
            final_message = result["message"][-1]
            agent_response_message = final_message.content if hasattr(final_message, 'content') else str(final_message)

        # Extract title
        document_title = presales.get('extracted_requirements', {}).get('project_summary', 'Technical Analysis Report')[:100]

        # Check if presales already has a chat_history_id (from when presales was created)
        existing_chat_history_id = analysis_link.get("chat_history_id") if analysis_link else None

        if existing_chat_history_id:
            # Presales already has a chat history - append full report to existing conversation
            logger.info(f"Appending full report to existing chat_history: {existing_chat_history_id}")

            # Get existing messages from the chat history
            existing_chat = await get_single_user_chat_history(
                chat_history_id=existing_chat_history_id,
                user_id=user_id,
                db=db
            )

            existing_messages_raw = existing_chat.get("message", []) if existing_chat else []
            # Parse JSON string if needed (database stores as JSON string)
            if isinstance(existing_messages_raw, str):
                try:
                    existing_messages = json.loads(existing_messages_raw)
                except json.JSONDecodeError:
                    existing_messages = []
            else:
                existing_messages = existing_messages_raw if isinstance(existing_messages_raw, list) else []

            # Append the full report message
            updated_messages = existing_messages + [
                {
                    "role": "assistant",
                    "content": agent_response_message,
                    "timestamp": datetime.now().isoformat(),
                    "type": "full_report",
                    "selected": True
                }
            ]

            # Update the chat history with appended message
            updated_chat_data = {
                "chat_history_id": existing_chat_history_id,
                "user_id": user_id,
                "document_id": presales["document_id"],
                "message": updated_messages,
                "title": document_title  # Update title to reflect full report
            }

            await save_chat_history(chat=updated_chat_data, db=db)
            chat_history_id = existing_chat_history_id
            logger.info(f"Appended full report to existing chat history: {chat_history_id}")

        else:
            # No existing chat history (legacy presales) - create new one
            logger.info(f"Creating new chat history for presales: {presales_id}")

            initial_chat_data = {
                "user_id": user_id,
                "document_id": presales["document_id"],
                "message": [
                    {
                        "role": "assistant",
                        "content": agent_response_message,
                        "timestamp": datetime.now().isoformat(),
                        "type": "full_report",
                        "selected": True
                    }
                ],
                "title": document_title
            }

            save_chat = await save_chat_history(chat=initial_chat_data, db=db)
            chat_history_id = save_chat["chat_history_id"]
            logger.info(f"Created new chat history: {chat_history_id}")

        # Update analysis link with full report (marks as generated)
        await update_analysis_link_with_full_report(
            presales_id=presales_id,
            chat_history_id=chat_history_id,
            db=db
        )

        # Chunk and embed for vector DB
        try:
            final_report_chunks = await chunking.chunk_text(text=agent_response_message)
            await vector_db.create_embeddings(
                texts=final_report_chunks,
                model=settings.EMBEDDING_MODEL,
                chat_history_id=chat_history_id
            )
            logger.info(f"Created embeddings for chat_history_id: {chat_history_id}")
        except Exception as e:
            logger.error(f"Error creating embeddings: {str(e)}")

        # Create summary
        try:
            summary_report = await main_report_summary(main_report=agent_response_message)
            summary_detail_report = {
                "chat_history_id": chat_history_id,
                "user_id": user_id,
                "report_content": agent_response_message,
                "summary_report": summary_report
            }
            await save_report_version(summary_report_details=summary_detail_report, db=db)
            logger.info(f"Saved report version for chat_history_id: {chat_history_id}")
        except Exception as e:
            logger.error(f"Error saving report version: {str(e)}")

        return {
            "message": agent_response_message,
            "document_id": presales["document_id"],
            "presales_id": presales_id,
            "chat_history_id": chat_history_id,
            "title": document_title,
            "status": "completed"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating full report: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating full report: {str(e)}"
        )


@router.get("/presales/{document_id}")
async def get_presales_for_document(
    document_id: str,
    current_token: dict = Depends(token_validator),
    db: Session = Depends(get_db)
):
    """
    Get pre-sales analysis for a specific document.

    Args:
        document_id: The document ID

    Returns:
        Pre-sales analysis data including brief, risks, and blind spots
    """
    user_id = current_token["regular_login_token"]["id"]

    try:
        presales = await get_presales_analysis(
            document_id=document_id,
            user_id=user_id,
            db=db
        )

        if not presales:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No pre-sales analysis found for document: {document_id}"
            )

        return presales

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving pre-sales analysis: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving pre-sales analysis: {str(e)}"
        )


@router.get("/presales/history/")
async def get_presales_history(
    limit: int = 20,
    offset: int = 0,
    current_token: dict = Depends(token_validator),
    db: Session = Depends(get_db)
):
    """
    Get user's pre-sales analysis history.

    Args:
        limit: Maximum number of records to return (default 20)
        offset: Number of records to skip (default 0)

    Returns:
        List of pre-sales analyses for the user
    """
    user_id = current_token["regular_login_token"]["id"]

    try:
        history = await get_user_presales_history(
            user_id=user_id,
            limit=limit,
            offset=offset,
            db=db
        )

        return {
            "user_id": user_id,
            "total": len(history),
            "limit": limit,
            "offset": offset,
            "analyses": history
        }

    except Exception as e:
        logger.error(f"Error retrieving pre-sales history: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving pre-sales history: {str(e)}"
        )


@router.post("/presales/{presales_id}/answers")
async def submit_kickstart_answers(
    presales_id: str,
    answers: dict,
    current_token: dict = Depends(token_validator),
    db: Session = Depends(get_db)
):
    """
    Submit answers to kickstart questions for a pre-sales analysis.

    Args:
        presales_id: The pre-sales analysis ID
        answers: Dict of question-answer pairs

    Returns:
        Updated analysis link
    """
    user_id = current_token["regular_login_token"]["id"]

    try:
        # Verify the presales analysis belongs to the user
        presales = await get_presales_by_id(
            presales_id=presales_id,
            user_id=user_id,
            db=db
        )

        if not presales:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Pre-sales analysis not found: {presales_id}"
            )

        # Save the answers
        result = await save_user_answers(
            presales_id=presales_id,
            user_answers=answers,
            db=db
        )

        logger.info(f"Saved answers for presales_id: {presales_id}")

        return {
            "presales_id": presales_id,
            "status": "answers_saved",
            "message": "Kickstart question answers saved successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving answers: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error saving answers: {str(e)}"
        )


@router.post("/presales/risks/{risk_id}/feedback")
async def submit_risk_feedback(
    risk_id: str,
    was_relevant: bool,
    feedback: Optional[str] = None,
    current_token: dict = Depends(token_validator),
    db: Session = Depends(get_db)
):
    """
    Submit feedback on whether a technology risk was relevant.

    This is used for passive learning - SAs can mark if the LLM-raised
    risk was actually relevant to the project.

    Args:
        risk_id: The technology risk ID
        was_relevant: True if the risk was actually relevant, False otherwise
        feedback: Optional text feedback explaining the relevance

    Returns:
        Updated risk record
    """
    user_id = current_token["regular_login_token"]["id"]

    try:
        result = await mark_risk_relevance(
            risk_id=risk_id,
            user_id=user_id,
            was_relevant=was_relevant,
            user_feedback=feedback,
            db=db
        )

        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Technology risk not found: {risk_id}"
            )

        logger.info(f"Marked risk {risk_id} as relevant={was_relevant}")

        return {
            "risk_id": risk_id,
            "was_relevant": was_relevant,
            "feedback": feedback,
            "status": "feedback_saved"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving risk feedback: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error saving risk feedback: {str(e)}"
        )


@router.post("/presales/{presales_id}/chat")
async def presales_chat(
    presales_id: str,
    message: str = Form(...),
    current_token: dict = Depends(token_validator),
    db: Session = Depends(get_db)
):
    """
    Enhanced chat with the pre-sales analysis.

    Features:
    - Conversation history persistence
    - Reference lookup (P1-1, Q3, etc.)
    - Answer capture from chat messages
    - Modification tracking

    Args:
        presales_id: The pre-sales analysis ID
        message: The user's question/message

    Returns:
        AI response with action metadata
    """
    from utils.presales_prompts import (
        PRESALES_CHAT_ENHANCED_PROMPT,
        PRESALES_CHAT_ROUTER_PROMPT
    )
    from langchain_openai import ChatOpenAI
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.output_parsers import JsonOutputParser, StrOutputParser
    import re

    user_id = current_token["regular_login_token"]["id"]
    logger.info(f"Presales chat for presales_id: {presales_id}, message: {message[:100]}...")

    try:
        # Get the presales analysis
        presales = await get_presales_by_id(presales_id=presales_id, user_id=user_id, db=db)

        if not presales:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Pre-sales analysis not found: {presales_id}"
            )

        # Get the linked chat_history_id from analysis_link
        analysis_link = await get_analysis_link_by_presales_id(
            presales_id=presales_id,
            user_id=user_id,
            db=db
        )

        chat_history_id = analysis_link.get("chat_history_id") if analysis_link else None
        document_id = presales.get("document_id")

        # Load existing conversation history
        conversation_history = []
        if chat_history_id:
            try:
                existing_chat = await get_single_user_chat_history(
                    user_id=user_id,
                    chat_history_id=chat_history_id,
                    db=db
                )
                if existing_chat and existing_chat.get("message"):
                    messages_raw = existing_chat.get("message", [])
                    if isinstance(messages_raw, str):
                        conversation_history = json.loads(messages_raw)
                    else:
                        conversation_history = messages_raw
                    # Filter to only chat messages (exclude initial presales_brief)
                    conversation_history = [
                        msg for msg in conversation_history
                        if msg.get("type") not in ["presales_brief", "full_report"]
                    ]
            except Exception as e:
                logger.warning(f"Could not load conversation history: {str(e)}")
                conversation_history = []

        # Build context from presales analysis
        presales_brief = presales.get("presales_brief", "")
        p1_blockers = presales.get("p1_blockers", [])
        kickstart_questions = presales.get("kickstart_questions", [])
        technology_risks = presales.get("technology_risks", [])
        scanned_requirements = presales.get("extracted_requirements", {})

        # Get questions with answers from database
        try:
            questions_list = await get_presales_questions(presales_id=presales_id, db=db, user_id=user_id)
            # get_presales_questions returns a list directly
            if not isinstance(questions_list, list):
                questions_list = []
        except Exception as e:
            logger.warning(f"Could not load questions: {str(e)}")
            questions_list = []

        # Detect referenced items (P1-1, Q3, etc.)
        referenced_item = None
        referenced_item_content = None

        # Check for P1 blocker references
        p1_match = re.search(r'P1-?(\d+)', message, re.IGNORECASE)
        if p1_match:
            p1_num = int(p1_match.group(1))
            if p1_blockers and 0 < p1_num <= len(p1_blockers):
                referenced_item = f"P1-{p1_num}"
                referenced_item_content = json.dumps(p1_blockers[p1_num - 1], indent=2)
                logger.info(f"Detected P1 blocker reference: {referenced_item}")

        # Check for kickstart question references
        q_match = re.search(r'(?:Q|question\s*)(\d+)', message, re.IGNORECASE)
        if q_match and not referenced_item:
            q_num = int(q_match.group(1))
            if kickstart_questions and 0 < q_num <= len(kickstart_questions):
                referenced_item = f"Q{q_num}"
                referenced_item_content = json.dumps(kickstart_questions[q_num - 1], indent=2)
                logger.info(f"Detected kickstart question reference: {referenced_item}")

        # Detect if user is providing an answer
        answer_detected = None
        answer_patterns = [
            r'(?:for|regarding|about)\s+(?:P1-?|Q)(\d+)[,:]?\s+(.+)',
            r'(?:the\s+)?answer\s+(?:to|for)\s+(?:P1-?|Q|question\s*)(\d+)\s+is[:\s]+(.+)',
            r'(?:P1-?|Q)(\d+)[:\s]+(.+?)(?:$|\.|,)',
        ]

        for pattern in answer_patterns:
            match = re.search(pattern, message, re.IGNORECASE | re.DOTALL)
            if match:
                q_ref = match.group(1)
                answer_content = match.group(2).strip()
                if answer_content and len(answer_content) > 5:  # Minimum answer length
                    # Determine if it's P1 or Q
                    if 'p1' in message.lower():
                        answer_detected = {"reference": f"P1-{q_ref}", "answer": answer_content}
                    else:
                        answer_detected = {"reference": f"Q{q_ref}", "answer": answer_content}
                    logger.info(f"Detected answer: {answer_detected}")
                    break

        # Save detected answer to database
        answer_saved = False
        if answer_detected:
            try:
                # Find the question_id for this reference
                ref = answer_detected["reference"]
                for q in questions_list:
                    if q.get("question_number") == ref:
                        await save_question_answer(
                            question_id=q["question_id"],
                            answer=answer_detected["answer"],
                            db=db
                        )
                        answer_saved = True
                        logger.info(f"Saved answer for {ref}")
                        break
            except Exception as e:
                logger.warning(f"Could not save answer: {str(e)}")

        # Format conversation history for prompt
        history_text = "No previous messages in this conversation."
        if conversation_history:
            history_lines = []
            for msg in conversation_history[-10:]:  # Last 10 messages
                role = msg.get("role", "unknown").capitalize()
                content = msg.get("content", "")[:500]  # Truncate long messages
                history_lines.append(f"**{role}**: {content}")
            history_text = "\n\n".join(history_lines)

        # Create the chat prompt
        llm = ChatOpenAI(
            api_key=settings.OPENAI_CHATGPT,
            model=settings.SUMMARIZATION_MODEL,  # Use faster model for chat
            temperature=0.3,
            request_timeout=60
        )

        prompt = ChatPromptTemplate.from_template(PRESALES_CHAT_ENHANCED_PROMPT)
        chain = prompt | llm | StrOutputParser()

        # Get response
        response_content = await chain.ainvoke({
            "presales_brief": presales_brief[:3000],  # Truncate for context window
            "p1_blockers": json.dumps(p1_blockers, indent=2),
            "kickstart_questions": json.dumps(kickstart_questions, indent=2),
            "technology_risks": json.dumps(technology_risks, indent=2),
            "scanned_requirements": json.dumps(scanned_requirements, indent=2)[:2000],
            "conversation_history": history_text,
            "user_message": message,
            "referenced_item": referenced_item_content or "No specific item referenced."
        })

        # If answer was saved, append confirmation to response
        if answer_saved and answer_detected:
            response_content += f"\n\n✅ **Answer recorded** for {answer_detected['reference']}: \"{answer_detected['answer'][:100]}{'...' if len(answer_detected['answer']) > 100 else ''}\""

        logger.info(f"Presales chat response generated, length: {len(response_content)}")

        # Save conversation to chat history
        if chat_history_id:
            try:
                # Append new messages to existing history
                new_messages = [
                    {
                        "role": "user",
                        "content": message,
                        "timestamp": datetime.now().isoformat(),
                        "type": "chat"
                    },
                    {
                        "role": "assistant",
                        "content": response_content,
                        "timestamp": datetime.now().isoformat(),
                        "type": "chat"
                    }
                ]

                # Get full message list including initial presales_brief message
                all_messages = []
                if conversation_history:
                    # Re-fetch to get all messages including presales_brief
                    existing_chat = await get_single_user_chat_history(
                        user_id=user_id,
                        chat_history_id=chat_history_id,
                        db=db
                    )
                    if existing_chat and existing_chat.get("message"):
                        msgs = existing_chat.get("message", [])
                        if isinstance(msgs, str):
                            all_messages = json.loads(msgs)
                        else:
                            all_messages = msgs

                all_messages.extend(new_messages)

                # Save updated conversation
                await save_chat_history(
                    chat={
                        "chat_history_id": chat_history_id,
                        "user_id": user_id,
                        "document_id": document_id,
                        "message": all_messages
                    },
                    db=db
                )
                logger.info(f"Saved conversation to chat_history_id: {chat_history_id}")
            except Exception as e:
                logger.warning(f"Could not save conversation history: {str(e)}")

        return {
            "presales_id": presales_id,
            "chat_history_id": chat_history_id,
            "user_message": message,
            "assistant_message": response_content,
            "timestamp": datetime.now().isoformat(),
            "action": {
                "referenced_item": referenced_item,
                "answer_detected": answer_detected,
                "answer_saved": answer_saved
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in presales chat: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing chat: {str(e)}"
        )


# =============================================================================
# PRESALES QUESTION MANAGEMENT & ANALYSIS ENDPOINTS
# =============================================================================

@router.get("/presales/{presales_id}/questions")
async def get_presales_questions_endpoint(
    presales_id: str,
    include_invalid: bool = True,
    current_token: dict = Depends(token_validator),
    db: Session = Depends(get_db)
):
    """
    Get all questions for a presales analysis.

    Args:
        presales_id: The presales analysis ID
        include_invalid: Whether to include invalidated questions

    Returns:
        List of questions with their current state
    """
    user_id = current_token["regular_login_token"]["id"]
    logger.info(f"Getting questions for presales: {presales_id}")

    questions = await get_presales_questions(presales_id, user_id, db, include_invalid)

    # Group questions by type and status
    p1_blockers = [q for q in questions if q["question_type"] == "p1_blocker"]
    kickstart = [q for q in questions if q["question_type"] == "kickstart"]
    invalid = [q for q in questions if q["status"] == "invalid"]

    return {
        "presales_id": presales_id,
        "questions": questions,
        "summary": {
            "total": len(questions),
            "p1_blockers": len(p1_blockers),
            "kickstart": len(kickstart),
            "answered": sum(1 for q in questions if q["status"] == "answered"),
            "pending": sum(1 for q in questions if q["status"] == "pending"),
            "invalid": len(invalid)
        }
    }


@router.post("/presales/{presales_id}/questions/answers")
async def save_question_answers(
    presales_id: str,
    answers: str = Form(...),
    current_token: dict = Depends(token_validator),
    db: Session = Depends(get_db)
):
    """
    Save answers for multiple questions.

    Args:
        presales_id: The presales analysis ID
        answers: JSON dict mapping frontend key (p1_0, question_0) or question_id -> answer text

    Returns:
        Dict with update status
    """
    import json as json_module

    user_id = current_token["regular_login_token"]["id"]
    logger.info(f"Saving answers for presales: {presales_id}")

    # Parse answers if it's a string
    if isinstance(answers, str):
        answers = json_module.loads(answers)

    logger.info(f"Received answers for {len(answers)} questions")
    logger.info(f"Received answer keys: {list(answers.keys())}")

    # Get all questions for this presales to map frontend keys to question_ids
    questions = await get_presales_questions(presales_id, user_id, db)

    # Build mappings from frontend keys to question_id
    # Frontend sends: p1_0, p1_1 (for P1 blockers, 0-indexed)
    # Frontend sends: question_0, question_1 (for kickstart questions, 0-indexed)
    # Backend has: question_number like P1-1, P1-2 (1-indexed) and Q1, Q2

    # Separate P1 blockers and kickstart questions by type
    p1_questions = [q for q in questions if q["question_type"] == "p1_blocker"]
    kickstart_questions = [q for q in questions if q["question_type"] == "kickstart"]

    # Sort by display_order to ensure correct mapping
    p1_questions.sort(key=lambda x: x["display_order"])
    kickstart_questions.sort(key=lambda x: x["display_order"])

    # Map frontend keys to actual question_ids
    mapped_answers = {}

    for key, answer in answers.items():
        question_id = None

        if key.startswith("p1_"):
            # P1 blocker: p1_0 -> index 0 -> first P1 question
            try:
                idx = int(key.split("_")[1])
                if idx < len(p1_questions):
                    question_id = p1_questions[idx]["question_id"]
                    logger.info(f"Mapped {key} -> P1 question {p1_questions[idx]['question_number']} ({question_id})")
            except (ValueError, IndexError) as e:
                logger.warning(f"Failed to parse P1 key {key}: {e}")

        elif key.startswith("question_"):
            # Kickstart question: question_0 -> index 0 -> first kickstart question
            try:
                idx = int(key.split("_")[1])
                if idx < len(kickstart_questions):
                    question_id = kickstart_questions[idx]["question_id"]
                    logger.info(f"Mapped {key} -> kickstart question {kickstart_questions[idx]['question_number']} ({question_id})")
            except (ValueError, IndexError) as e:
                logger.warning(f"Failed to parse kickstart key {key}: {e}")

        else:
            # Assume it's already a question_id (UUID)
            question_id = key
            logger.info(f"Using key as question_id: {key}")

        if question_id and answer:  # Only save non-empty answers
            mapped_answers[question_id] = answer

    logger.info(f"Mapped {len(mapped_answers)} answers to question_ids")

    if not mapped_answers:
        return {
            "presales_id": presales_id,
            "status": "success",
            "updated_count": 0,
            "history_records": 0,
            "message": "No valid answers to save"
        }

    result = await update_question_answers(presales_id, user_id, mapped_answers, db)

    return {
        "presales_id": presales_id,
        "status": "success",
        **result
    }


@router.post("/presales/{presales_id}/analyze")
async def analyze_presales_answers(
    presales_id: str,
    current_token: dict = Depends(token_validator),
    db: Session = Depends(get_db)
):
    """
    Analyze answers and calculate readiness for full report.

    This endpoint:
    1. Gets all questions and answers
    2. Runs the answer analyzer agent
    3. Identifies contradictions, vague answers, invalidated questions
    4. Calculates readiness score
    5. Generates list of assumptions

    Returns:
        Readiness report with all analysis results
    """
    from agents.answer_analyzer import analyze_answers, analyze_answers_quick

    user_id = current_token["regular_login_token"]["id"]
    logger.info(f"Analyzing answers for presales: {presales_id}")

    try:
        # Get presales data
        presales = await get_presales_by_id(presales_id, user_id, db)
        if not presales:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Presales analysis not found: {presales_id}"
            )

        # Get questions
        questions = await get_presales_questions(presales_id, user_id, db)

        # Get document for context
        document = ""
        if presales.get("extracted_requirements"):
            document = json.dumps(presales["extracted_requirements"])

        # Run full analysis
        analysis_result = await analyze_answers(
            document=document,
            scanned_requirements=presales.get("extracted_requirements", {}),
            questions=questions,
            timeout=120
        )

        # Update question statuses based on invalidation
        for inv_q in analysis_result.invalidated_questions:
            question_number = inv_q.get("question_id")
            # Find the actual question_id from question_number
            matching_q = next(
                (q for q in questions if q["question_number"] == question_number),
                None
            )
            if matching_q:
                await update_question_status(
                    question_id=matching_q["question_id"],
                    user_id=user_id,
                    status_value="invalid",
                    reason=inv_q.get("reason", ""),
                    invalidated_by=inv_q.get("invalidated_by", ""),
                    db=db
                )

        # Update question quality flags
        for vague in analysis_result.vague_answers:
            question_number = vague.get("question_id")
            matching_q = next(
                (q for q in questions if q["question_number"] == question_number),
                None
            )
            if matching_q:
                # Update answer quality
                q_record = db.query(models.PresalesQuestion).filter(
                    models.PresalesQuestion.question_id == matching_q["question_id"]
                ).first()
                if q_record:
                    q_record.answer_quality = "vague"
                    q_record.answer_feedback = vague.get("issue", "")
                    db.commit()

        # Update presales readiness
        await update_presales_readiness(
            presales_id=presales_id,
            readiness_score=analysis_result.readiness_score,
            readiness_status=analysis_result.readiness_status,
            assumptions_list=analysis_result.assumptions,
            contradictions_list=analysis_result.contradictions,
            vague_answers_list=analysis_result.vague_answers,
            db=db
        )

        # Save analysis history
        await save_analysis_history(
            presales_id=presales_id,
            user_id=user_id,
            analysis_result=analysis_result.to_dict(),
            questions_snapshot=questions,
            processing_time_ms=analysis_result.processing_time_ms,
            db=db
        )

        logger.info(f"Analysis complete for {presales_id}: score={analysis_result.readiness_score}")

        # Get updated questions
        updated_questions = await get_presales_questions(presales_id, user_id, db)

        return {
            "presales_id": presales_id,
            "readiness": {
                "score": analysis_result.readiness_score,
                "status": analysis_result.readiness_status,
                "summary": analysis_result.readiness.get("summary", "")
            },
            "contradictions": analysis_result.contradictions,
            "vague_answers": analysis_result.vague_answers,
            "invalidated_questions": analysis_result.invalidated_questions,
            "assumptions": analysis_result.assumptions,
            "follow_up_questions": analysis_result.follow_up_questions,
            "recommendations": analysis_result.recommendations,
            "questions": updated_questions,
            "can_generate_report": analysis_result.can_generate_report,
            "processing_time_ms": analysis_result.processing_time_ms
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error analyzing presales answers: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error analyzing answers: {str(e)}"
        )


@router.post("/presales/{presales_id}/questions/{question_id}/restore")
async def restore_presales_question(
    presales_id: str,
    question_id: str,
    current_token: dict = Depends(token_validator),
    db: Session = Depends(get_db)
):
    """
    Restore an invalidated question.

    Args:
        presales_id: The presales analysis ID
        question_id: The question ID to restore

    Returns:
        Dict with restored question status
    """
    user_id = current_token["regular_login_token"]["id"]
    logger.info(f"Restoring question {question_id} for presales: {presales_id}")

    result = await restore_question(question_id, user_id, db)

    return {
        "presales_id": presales_id,
        **result
    }


@router.get("/presales/{presales_id}/full")
async def get_presales_full(
    presales_id: str,
    current_token: dict = Depends(token_validator),
    db: Session = Depends(get_db)
):
    """
    Get full presales data including questions, readiness, and analysis results.

    Returns complete state for frontend display.
    """
    user_id = current_token["regular_login_token"]["id"]
    logger.info(f"Getting full presales data for: {presales_id}")

    data = await get_presales_with_questions(presales_id, user_id, db)

    # Add quick readiness calculation if not yet analyzed
    if data.get("readiness_status") == "not_analyzed":
        from agents.answer_analyzer import analyze_answers_quick
        quick_readiness = await analyze_answers_quick(data.get("questions", []))
        data["quick_readiness"] = quick_readiness.get("readiness")

    return data


@router.get("/task_status/{task_id}")
async def get_task_status(
    task_id: str,
    current_token: dict = Depends(token_validator)
):
    """Get the status of a processing task"""
    logger.info(f"Checking status for task_id: {task_id}")
    logger.info(f"Available task IDs: {list(task_status.keys())}")
    
    if task_id not in task_status:
        # Check if the task was completed and has a result
        completed_task = next((t for t in task_status.values() 
                              if t.get("status") == "completed" and 
                                 t.get("result", {}).get("document_id") == task_id), None)
        
        if completed_task:
            logger.info(f"Found completed task with matching document_id: {task_id}")
            return completed_task
            
        # If we still can't find it, return a more helpful error
        logger.error(f"Task not found: {task_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task not found. Available tasks: {len(task_status)}"
        )
    
    logger.info(f"Returning status for task_id: {task_id}")
    return task_status[task_id]

@router.post("/jira/get_user")
async def get_user_details(
    request: Request,
    current_user: dict = Depends(token_validator),  # App authentication
    db: Session = Depends(get_db)
):
    """Get Jira user details using stored token"""
    try:
        # Get Jira token from Authorization header
        auth_header = request.headers.get("Jira-Authorization")
        if not auth_header:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Jira token not provided"
            )
            
        # Validate Jira token
        jira_token = auth_header.split("Bearer ")[1]
        jira_payload = token_validator(request=jira_token)
        print(f"jira_payload: {jira_payload}")
        
        # Use the access token stored in the Jira JWT
        user_info = await get_jira_user_info(jira_payload["jira_access_token"])
        
        return {
            "message": "Jira user details retrieved",
            "jira_email": user_info.get("email"),
            "account_id": user_info.get("account_id")
        }
        
    except Exception as e:
        logger.error(f"Failed to get Jira user details: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get Jira user details: {str(e)}"
        )

@router.get("/status-page/{task_id}", response_class=HTMLResponse)
async def task_status_page(task_id: str, token: str = None):
    """
    Renders an HTML page that polls for task status and communicates with parent window.
    This bypasses ngrok security restrictions.
    """
    # Validate token (simplified for brevity - implement proper validation)
    if not token:
        return HTMLResponse(content="Unauthorized", status_code=401)
    
    # Create HTML page that polls for status and communicates with parent
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Processing Status</title>
        <script>
            const taskId = "{task_id}";
            const token = "{token}";
            const apiUrl = "http://localhost:8080";  // Updated to correct port
            
            async function pollStatus() {{
                try {{
                    console.log("Polling status for task:", taskId);
                    const response = await fetch(`${{apiUrl}}/task_status/${{taskId}}`, {{
                        headers: {{
                            'Authorization': `Bearer ${{token}}`
                        }}
                    }});
                    
                    if (!response.ok) {{
                        throw new Error(`Status polling failed: ${{response.status}}`);
                    }}
                    
                    const data = await response.json();
                    console.log("Status update:", data);
                    
                    // Send data to parent window
                    window.opener.postMessage({{
                        type: 'task_status_update',
                        ...data
                    }}, "*");
                    
                    // Continue polling if not complete
                    if (data.status !== 'completed' && data.status !== 'error') {{
                        setTimeout(pollStatus, 1000);
                    }}
                }} catch (error) {{
                    console.error("Error polling status:", error);
                    
                    // Send error to parent
                    window.opener.postMessage({{
                        type: 'task_status_update',
                        status: 'error',
                        message: `Status polling failed: ${{error.message}}`
                    }}, "*");
                }}
            }}
            
            // Start polling when page loads
            window.onload = function() {{
                console.log("Status page loaded, starting polling");
                pollStatus();
            }};
        </script>
    </head>
    <body style="background-color: #f0f0f0; padding: 20px; font-family: Arial, sans-serif;">
        <h1>Processing your document...</h1>
        <p>This window will close automatically when processing is complete.</p>
        <p>Task ID: {task_id}</p>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html_content)


@router.post('/chat')
async def add_chat_history(request: ChatHistoryDetails,db:Session=Depends(get_db)):
    try:
        chat = request.model_dump()
        logger.info(f"got the details in api ,saving the chat history for user: {chat['user_id']}")
        save_chat = await save_chat_history(chat=chat, db=db)
        print(f"save_chat: {save_chat}")
        return {"status":save_chat["status"], "chat_history_id":save_chat["chat_history_id"], "user_id":save_chat["user_id"],"message":save_chat["message"]}
    except Exception as e:
        logger.error(f"error occured while saving the chat history for user: {chat['user_id']}, error: {str(e)}")
        raise HTTPException(status_code=400, detail=f"details are missing: {str(e)}")
    

# @router.post('/chat')
# async def add_chat_history(request: ChatHistoryDetails,db:Session=Depends(get_db)):
#     chat = request.model_dump()
#     if chat["chat_history_id"] is None:
#         logger.info(f"This is the first request to add it to chat, {chat['chat_history_id']}, for request: {chat}")
#         print(f"This is the first request to add it to chat, {chat['chat_history_id']}")
#     if chat["chat_history_id"] is not None:
#         logger.info(f"This is the follow up request to add to existing chat history: {chat['chat_history_id']}, for request: {chat}")
#         print(f"This is the follow up request to add to existing chat history: {chat['chat_history_id']}")
    # try:
        
    #     logger.info(f"got the details in api ,saving the chat history for user: {chat['user_id']}")
        # save_chat = await save_chat_history(chat=chat, db=db)
    #     logger.info(f"save chat details: {save_chat}")

    #     if not save_chat:
    #         logger.error(f"Failed to save chat history for user: {chat['user_id']} due to no response in save chat")
    #         raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to save chat history LLM didnt respond correctly about the document")
    #     else:
    #         try:
    #             final_report_chunks = await chunking.chunk_text(text=chat['message'][0]['content'])
    #             logger.info(f"chunking complete for chat_history_id:{save_chat['chat_history_id']}, total chunks: {len(final_report_chunks)}")
    #         except Exception as e:
    #             logger.error(f"Error during chunking for chat_history_id: {save_chat['chat_history_id']}, error: {e}")
    #             raise HTTPException(status_code= status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"chunking failed: {e}")
    #         try:
    #             vectordb_resp = await vector_db.create_embeddings(
    #                 texts= final_report_chunks,
    #                 model=settings.EMBEDDING_MODEL,
    #                 chat_history_id=save_chat["chat_history_id"]
    #             )
    #             logger.info(f"successfully created embedding and added to vector DB for chat_history_id: {save_chat['chat_history_id']}")
    #         except Exception as e:
    #             logger.error(f"Error during embedding creation for chat_history_id: {save_chat['chat_history_id']}, error: {e}")
    #             raise HTTPException(status_code= status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"embedding creation failed: {e}")
    #             # vector_db.create_embeddings(text=chat['message'][0]['content'], chat_history_id=save_chat["chat_history_id"])
    #         logger.info(f"successfully saved the chat history for user: {chat['user_id']} and chat_history_id: {save_chat['chat_history_id']}")
        
    #     #creating the summary of the final report chunks
    #     try:
    #         summary_report = await main_report_summary(main_report= chat['message'][0]['content'])
    #         summary_detail_report = {
    #             "chat_history_id": save_chat["chat_history_id"],
    #             "user_id": save_chat["user_id"],
    #             "report_content" : chat['message'][0]['content'],
    #             "summary_report": summary_report

    #         }
    #         logger.info(f"summary_detail_report: {summary_detail_report}")
    #         logger.info(f"Successfully created the summary report for chat_history_id: {save_chat['chat_history_id']}")
    #         await save_report_version(summary_report_details=summary_detail_report, db=db)
    #         logger.info(f"Successfully saved the summary report for chat_history_id: {save_chat['chat_history_id']}")
    #     except Exception as e:
    #         logger.error(f"Error during summary report creation and saving for chat_history_id: {save_chat['chat_history_id']}, error:{str(e)}")
    #         raise HTTPException(status_code= status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error occured on creating and saving the summary report: {str(e)}")

    #     return {"status":save_chat["status"], "chat_history_id":save_chat["chat_history_id"], "user_id":save_chat["user_id"],"message":save_chat["message"]}
    # except Exception as e:
    #     logger.error(f"error occured while saving the chat history for user: {chat['user_id']}, error: {str(e)}")
    #     raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"details are missing: {str(e)}")
    

@router.delete('/chat/{chat_id}')
async def chat_delete(chat_id:str,db:Session=Depends(get_db),current_user:dict=Depends(token_validator)):
    try:
        
        deleted_details = await delete_chat_history(user_id = current_user["regular_login_token"]["id"], chat_history_id=chat_id, db=db)
        logger.info(f"deleted the chat history for user: {current_user['regular_login_token']['id']}, chat_id: {chat_id}")
        return {"status":deleted_details["status"]}
    except Exception as e:
        logger.error(f"error occured while deleting the chat history for user: {current_user['regular_login_token']['id']}, error: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Provided incorrect Details") 
        
@router.get('/chat')
async def get_user_chat_history(current_user = Depends(token_validator), db:Session=Depends(get_db)):
    chat_records = await get_user_chat_history_details(user_id=current_user["regular_login_token"]["id"], db=db)
    return {"user_details": chat_records}

@router.get('/chat/{chat_history_id}')
async def get_user_chat_history_by_id(chat_history_id:str,current_user = Depends(token_validator), db:Session=Depends(get_db)):
    single_record = await get_single_user_chat_history(user_id=current_user["regular_login_token"]["id"], chat_history_id=chat_history_id, db=db)
    return {"user_details": single_record}

# @router.post('/chat-with-doc')
# async def conversation_with_doc(request:ChatHistoryDetails,current_user = Depends(token_validator), db:Session=Depends(get_db)):
#     """
#     Selected context is used to chat with the LLM
#     Frontend sends ALL messages with 'selected: true/false' field
#     Backend extracts selected messages for AI, saves full conversation with selection state

#     Args:
#     request: ChatHistoryDetails,
#     current_user: dict,
#     db: Session,

#     Expected payload from frontend:
#     {
#         'chat_history_id': 'xxx',
#         'user_id': 'xxx',
#         'document_id': 'xxx',
#         'message': [
#             {'role': 'user', 'content': 'Should I use vector DB?', 'timestamp': '...', 'selected': True},
#             {'role': 'assistant', 'content': 'Yes, use vector DB', 'timestamp': '...', 'selected': True},
#             {'role': 'user', 'content': 'Actually skip vector DB', 'timestamp': '...', 'selected': False},
#             {'role': 'user', 'content': 'What about Redis?', 'timestamp': '...', 'selected': True}
#         ],
#         'title': 'Project Planning Chat'
#     }

#     Returns:
#     Dict: LLM response to user question regarding the document and its recommendation
#     """
#     LLM_response = None
#     try:
#         if current_user["regular_login_token"]["id"] != request.user_id:
#             raise HTTPException(status_code=400, detail=f"User ID mismatch")

#         chat_context = request.model_dump()
#         logger.info(f"Processing chat-with-doc for user: {request.user_id}, chat_history_id: {request.chat_history_id}")
#         logger.info(f"Total messages: {len(chat_context['message'])}")

#         # Extract ONLY selected messages for LLM processing
#         selected_messages = [msg for msg in chat_context["message"] if msg.get("selected", True)]
#         logger.info(f"Selected messages for AI: {len(selected_messages)}")

#         # Prepare messages for LLM (without 'selected' field)
#         selected_messages_for_llm = [
#             {"role": msg["role"], "content": msg["content"]}
#             for msg in selected_messages
#         ]

#         # Get LLM response based on SELECTED messages only
#         LLM_response = await ProjectScopingAgent.chat_with_doc(context=selected_messages_for_llm)

#         # Append assistant response to message list (marked as selected by default)
#         new_assistant_message = {
#             "role": "assistant",
#             "content": LLM_response.get('message', str(LLM_response)),
#             "timestamp": datetime.now().isoformat(),
#             "selected": True  # New AI responses are selected by default
#         }
#         chat_context["message"].append(new_assistant_message)

#         # Save FULL conversation with selection state to chat_history
#         await save_chat_history(chat=chat_context, db=db)
#         logger.info(f"Saved full conversation to chat_history")

#         # Save ONLY selected messages to selected_chat (for data collection)
#         selected_only_data = {
#             "chat_history_id": chat_context["chat_history_id"],
#             "user_id": chat_context["user_id"],
#             "document_id": chat_context["document_id"],
#             "message": [msg for msg in chat_context["message"] if msg.get("selected", False)],
#             "title": chat_context.get("title")
#         }
#         await save_chat_with_doc(chat_context=selected_only_data, db=db)
#         logger.info(f"Saved selected messages to selected_chat ({len(selected_only_data['message'])} messages)")

#         return {"message": new_assistant_message["content"]}

#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.error(f"Error in chat-with-doc: {str(e)}")
#         raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

# @router.post('/chat-with-doc')
# async def conversation_with_doc(request:ChatHistoryDetails,current_user = Depends(token_validator), db:Session=Depends(get_db)):

#     if current_user['regular_login_token']['id'] == request.user_id:
#         chat_context = request.model_dump()
#         logger.info(f"chat_context: {chat_context}")

#         #Threshold for token count to decide whether to summarize or not
#         token_count = await count_token(chat_context["message"][1:])
#         logger.info(f"Total token count in the conversation: {token_count}")
#         if token_count > 3000:
#             logger.info(f"Token count exceeds threshold, generating conversation summary")
#             try:
#                 conversation_summary = await conversation_summary_llm(conversation=chat_context["message"][1:])
#                 logger.info(f"Conversation summary generated")
#                 chat_messages_list = conversation_summary
#             except Exception as e:
#                 logger.error(f"Error generating conversation summary: {str(e)}, user_id: {chat_context['user_id']}, chat_history_id: {chat_context['chat_history_id']}")
#                 raise HTTPException(status_code=500, detail= f" Error generatingconversation summary: {str(e)}")
#         else:
#             chat_messages_list = chat_context["message"][1:]

#         # pull details from DB based on chat history id, main report summary.

#         try:
#             report_summary = await get_summary_report(chat_history_id=chat_context["chat_history_id"], db=db)
#             logger.info(f"Successfully retrieved the latest report summary from DB for chat_history_id: {chat_context['chat_history_id']}")
#         except Exception as e:
#             logger.error(f"Error retrieving report summary from DB for chat_history_id: {chat_context['chat_history_id']}, error: {str(e)}")

#             raise HTTPException(status_code=500, detail= f"Error retrieving report summary: {str(e)}")
        
#         #check for summary or throw and error if i dont get the data since every report will have summary
#         if not report_summary:
#             logger.error(f" No report summary found for chat_history_id: {chat_context['chat_history_id']}")
#             raise HTTPException(status_code=404, detail = f"No report summary found for chat_history_id: {chat_context['chat_history_id']}")
        
#         try:
#             router_llm_response = await router_query_llm(
#                 user_message = chat_context["message"][-1]["content"],
#                 conversation_summary= chat_messages_list,
#                 report_summary= report_summary
#             )
#             logger.info(f"Router LLM response received for chat_history_id: {chat_context['chat_history_id']}")
#             return {"message": f"{router_llm_response}"}
#         except Exception as e:
#             logger.error(f"Error in router LLM processing: {str(e)}, chat_history_id: {chat_context['chat_history_id']}")
#             raise HTTPException(status_code=500, detail= f"Error in router LLM processing: {str(e)}")
        
        
            




            # # adding router LLM to direct the query to appropriate model
            # router_response = await router_query_llm(
            #     user_query = chat_context["message"][-1]["content"],

            # )


# Token threshold for conversation summarization (configurable)
CONVERSATION_TOKEN_THRESHOLD = 3000


@router.post('/chat-with-doc')
async def conversation_with_doc_v2(
    request: ChatHistoryDetails,
    current_user = Depends(token_validator),
    db: Session = Depends(get_db)
):
    """
    Combined chat endpoint with:
    - Selected message filtering
    - Token counting and conversation summarization
    - Report summary retrieval
    - Router LLM for action classification
    - Action-based response generation

    Flow:
    1. Validate user
    2. Extract selected messages
    3. Count tokens, summarize if over threshold
    4. Get report summary from DB
    5. Route query to determine action type
    6. Generate response based on action
    7. Save conversation history
    8. Return response

    Args:
        request: ChatHistoryDetails with message array containing 'selected' field
        current_user: Authenticated user from token
        db: Database session

    Returns:
        Dict with AI response message
    """
    try:
        # 1. Validate user
        if current_user["regular_login_token"]["id"] != request.user_id:
            raise HTTPException(status_code=400, detail="User ID mismatch")

        chat_context = request.model_dump()
        logger.info(f"Processing chat-with-docs-v2 for user: {request.user_id}, chat_history_id: {request.chat_history_id}")
        logger.info(f"Total messages received: {len(chat_context['message'])}")

        # 2. Extract ONLY selected messages for processing
        # Filter out 'full_report' type messages - they are too large and we have the report summary from DB
        selected_messages = [
            msg for msg in chat_context["message"]
            if msg.get("selected", True) and msg.get("type") != "full_report"
        ]
        logger.info(f"Selected messages for processing: {len(selected_messages)} (excluded full_report messages)")

        if len(selected_messages) == 0:
            raise HTTPException(status_code=400, detail="No selected messages to process")

        # 3. Token counting on selected messages (skip first message - initial report)
        messages_for_processing = selected_messages[1:] if len(selected_messages) > 1 else []

        if len(messages_for_processing) > 0:
            token_count = await count_token(messages_for_processing)
            logger.info(f"Token count for selected messages: {token_count}")

            # Summarize conversation if over threshold
            if token_count > CONVERSATION_TOKEN_THRESHOLD:
                logger.info(f"Token count ({token_count}) exceeds threshold ({CONVERSATION_TOKEN_THRESHOLD}), summarizing conversation")
                try:
                    conversation_context = await conversation_summary_llm(conversation=messages_for_processing)
                    logger.info("Conversation summary generated successfully")
                except Exception as e:
                    logger.error(f"Error generating conversation summary: {str(e)}")
                    raise HTTPException(status_code=500, detail=f"Error generating conversation summary: {str(e)}")
            else:
                conversation_context = messages_for_processing
        else:
            conversation_context = []

        # 4. Retrieve report summary from DB
        try:
            report_summary = await get_summary_report(chat_history_id=chat_context["chat_history_id"], db=db)
            logger.info(f"Retrieved report summary for chat_history_id: {chat_context['chat_history_id']}")
        except Exception as e:
            logger.error(f"Error retrieving report summary: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error retrieving report summary: {str(e)}")

        if not report_summary:
            logger.error(f"No report summary found for chat_history_id: {chat_context['chat_history_id']}")
            raise HTTPException(status_code=404, detail=f"No report summary found for chat_history_id: {chat_context['chat_history_id']}")

        # Get the latest user message
        user_message = chat_context["message"][-1]["content"]

        # 5. Route query to determine action type
        # Use summary_report (compressed) not the full report_content
        try:
            router_response = await router_query_llm(
                user_message=user_message,
                conversation_summary=conversation_context,
                report_summary=report_summary.summary_report if hasattr(report_summary, 'summary_report') else report_summary
            )
            action = router_response.get("action", "general_discussion")
            action_reason = router_response.get("reason", "")
            logger.info(f"Router classified action: {action}, reason: {action_reason}")
        except Exception as e:
            logger.error(f"Error in router LLM: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error in router LLM: {str(e)}")

        # 6. Handle action-specific processing
        retrieved_context = "N/A"
        llm_response = None
        pending_changes_info = None

        # ============================================================
        # CHANGE TRACKING LOGIC (Phase 1 - Hybrid Approach)
        # ============================================================

        # Check if this is a change tracking action (modify_*, correct_*)
        if is_change_tracking_action(action):
            logger.info(f"Action {action} requires change tracking")

            # Get existing pending changes
            existing_changes = await get_pending_changes(chat_context["chat_history_id"], db)
            logger.info(f"Existing pending changes: {len(existing_changes)}")

            # Get affected sections for this change type
            affected_sections = get_affected_sections(action)

            # Create the change record
            change_record = {
                "type": action,
                "user_request": user_message,
                "affected_sections": affected_sections,
                "timestamp": datetime.now().isoformat(),
                "status": "pending"
            }

            # Add the change to pending
            try:
                add_result = await add_pending_change(
                    chat_history_id=chat_context["chat_history_id"],
                    change=change_record,
                    db=db
                )
                change_id = add_result["change_id"]
                logger.info(f"Added pending change: {change_id}")
            except Exception as e:
                logger.error(f"Error adding pending change: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Error tracking change: {str(e)}")

            # Check for conflicts after adding the new change
            all_changes = add_result["pending_changes"]
            conflicts = detect_conflicts(all_changes)

            if conflicts:
                logger.info(f"Detected {len(conflicts)} conflicts in pending changes")
                # Generate conflict resolution prompt
                try:
                    llm_response = await generate_conflict_resolution(
                        conflicts=conflicts,
                        all_pending_changes=all_changes
                    )
                    action = "conflict_detected"  # Update action for response metadata
                except Exception as e:
                    logger.error(f"Error generating conflict resolution: {str(e)}")
                    llm_response = f"I've tracked your change, but detected potential conflicts with previous changes. Please review your pending changes."
            else:
                # Generate change acknowledgment
                try:
                    llm_response = await generate_change_acknowledgment(
                        change_type=action,
                        user_request=user_message,
                        affected_sections=affected_sections,
                        existing_pending_changes=existing_changes,
                        change_id=change_id
                    )
                except Exception as e:
                    logger.error(f"Error generating acknowledgment: {str(e)}")
                    llm_response = f"**Change Tracked** ✓\n\n**ID:** {change_id}\n**Request:** {user_message}\n\nWhen ready, say **\"regenerate report\"** to apply all changes."

            # Include pending changes info in response
            pending_changes_info = {
                "total_pending": len(all_changes),
                "has_conflicts": len(conflicts) > 0,
                "latest_change_id": change_id
            }

        # ============================================================
        # UNDO/ROLLBACK ACTIONS
        # ============================================================

        # Handle undo_last_change action
        elif action == "undo_last_change":
            logger.info("Processing undo_last_change action")
            try:
                result = await remove_last_pending_change(chat_context["chat_history_id"], db)

                if result["status"] == "no_changes":
                    llm_response = "**No Changes to Undo**\n\nThere are no pending changes to undo. Your current report has no uncommitted modifications."
                else:
                    removed = result["removed_change"]
                    remaining = result["remaining_count"]
                    llm_response = f"""**Change Undone** ↩️

**Removed:** {removed.get('user_request', 'Unknown change')}
**Change ID:** {removed.get('id', 'N/A')}

**Remaining pending changes:** {remaining}

{f"When ready, say **'regenerate report'** to apply the remaining changes." if remaining > 0 else "No pending changes remaining."}"""

                pending_changes_info = {
                    "total_pending": result["remaining_count"],
                    "has_conflicts": False,
                    "undone_change": result.get("removed_change")
                }
                logger.info(f"Undid last change, remaining: {result['remaining_count']}")
            except Exception as e:
                logger.error(f"Error undoing last change: {str(e)}")
                llm_response = f"I encountered an error while trying to undo the last change: {str(e)}"

        # Handle undo_specific_change action
        elif action == "undo_specific_change":
            logger.info("Processing undo_specific_change action")
            # Extract change ID from user message (e.g., CHG-001, CHG-002)
            import re
            change_id_match = re.search(r'CHG-(\d+)', user_message, re.IGNORECASE)

            if change_id_match:
                change_id = f"CHG-{change_id_match.group(1).zfill(3)}"
                try:
                    result = await remove_pending_change(chat_context["chat_history_id"], change_id, db)
                    llm_response = f"""**Change Removed** ↩️

**Removed Change ID:** {change_id}

**Remaining pending changes:** {result['remaining_count']}

{f"When ready, say **'regenerate report'** to apply the remaining changes." if result['remaining_count'] > 0 else "No pending changes remaining."}"""

                    pending_changes_info = {
                        "total_pending": result["remaining_count"],
                        "has_conflicts": False,
                        "removed_change_id": change_id
                    }
                    logger.info(f"Removed specific change {change_id}")
                except HTTPException as he:
                    if he.status_code == 404:
                        llm_response = f"**Change Not Found**\n\nI couldn't find a pending change with ID **{change_id}**. Use **'show pending changes'** to see all available changes."
                    else:
                        raise
                except Exception as e:
                    logger.error(f"Error removing change {change_id}: {str(e)}")
                    llm_response = f"I encountered an error while trying to remove change {change_id}: {str(e)}"
            else:
                # No change ID found, show pending changes instead
                pending_changes = await get_pending_changes(chat_context["chat_history_id"], db)
                if pending_changes:
                    changes_list = "\n".join([f"- **{c.get('id')}**: {c.get('user_request', 'Unknown')}" for c in pending_changes])
                    llm_response = f"""**Which change would you like to remove?**

Please specify a change ID (e.g., "remove CHG-001").

**Current Pending Changes:**
{changes_list}"""
                else:
                    llm_response = "**No Pending Changes**\n\nThere are no pending changes to remove."

        # Handle clear_all_changes action
        elif action == "clear_all_changes":
            logger.info("Processing clear_all_changes action")
            try:
                # First get current changes for logging
                current_changes = await get_pending_changes(chat_context["chat_history_id"], db)
                cleared_count = len(current_changes)

                if cleared_count == 0:
                    llm_response = "**No Pending Changes**\n\nThere are no pending changes to clear. Your report is clean."
                else:
                    result = await clear_pending_changes(chat_context["chat_history_id"], db)
                    llm_response = f"""**All Changes Cleared** 🗑️

**Removed:** {cleared_count} pending change(s)

Your report is now back to the last generated version. Any modifications you previously requested have been discarded.

Feel free to start fresh with new modification requests."""

                pending_changes_info = {
                    "total_pending": 0,
                    "has_conflicts": False,
                    "cleared_count": cleared_count
                }
                logger.info(f"Cleared all pending changes, count: {cleared_count}")
            except Exception as e:
                logger.error(f"Error clearing pending changes: {str(e)}")
                llm_response = f"I encountered an error while trying to clear all changes: {str(e)}"

        # Handle show_pending_changes action
        elif action == "show_pending_changes":
            logger.info("Processing show_pending_changes action")
            try:
                pending_changes = await get_pending_changes(chat_context["chat_history_id"], db)

                if not pending_changes:
                    llm_response = """**No Pending Changes**

Your report has no uncommitted modifications. The current version is up to date.

To make changes, you can:
- Request architecture changes (e.g., "Use PostgreSQL instead of MongoDB")
- Modify requirements (e.g., "Add real-time notification support")
- Correct assumptions (e.g., "We're using AWS, not Azure")"""
                else:
                    # Format changes list
                    changes_list = []
                    for i, change in enumerate(pending_changes, 1):
                        change_id = change.get('id', f'CHG-{i:03d}')
                        change_type = change.get('type', 'unknown').replace('_', ' ').title()
                        request = change.get('user_request', 'Unknown change')
                        timestamp = change.get('timestamp', 'N/A')
                        affected = ', '.join(change.get('affected_sections', []))

                        changes_list.append(f"""**{i}. {change_id}** ({change_type})
   - Request: {request}
   - Affects: {affected}
   - Added: {timestamp[:16] if len(timestamp) > 16 else timestamp}""")

                    # Check for conflicts
                    conflicts = detect_conflicts(pending_changes)
                    conflict_warning = ""
                    if conflicts:
                        conflict_warning = f"\n\n⚠️ **Warning:** {len(conflicts)} potential conflict(s) detected. Please review before regenerating."

                    llm_response = f"""**Pending Changes** ({len(pending_changes)})
{conflict_warning}

{chr(10).join(changes_list)}

---

**Actions:**
- Say **"regenerate report"** to apply all changes
- Say **"undo last change"** to remove the most recent change
- Say **"remove CHG-XXX"** to remove a specific change
- Say **"clear all changes"** to discard all modifications"""

                pending_changes_info = {
                    "total_pending": len(pending_changes),
                    "has_conflicts": len(detect_conflicts(pending_changes)) > 0 if pending_changes else False,
                    "changes": pending_changes
                }
                logger.info(f"Showed {len(pending_changes)} pending changes")
            except Exception as e:
                logger.error(f"Error getting pending changes: {str(e)}")
                llm_response = f"I encountered an error while retrieving pending changes: {str(e)}"

        # Handle regenerate_full_report action
        elif action == "regenerate_full_report":
            logger.info("Processing regenerate_full_report action")

            # Get all pending changes
            pending_changes = await get_pending_changes(chat_context["chat_history_id"], db)

            if not pending_changes:
                # No pending changes - show the full current report
                try:
                    current_report_content = report_summary.report_content if hasattr(report_summary, 'report_content') else None
                    current_version = report_summary.version_number if hasattr(report_summary, 'version_number') else 1

                    if current_report_content:
                        llm_response = f"""**Current Report (Version {current_version})** 📄

There are no pending changes to apply. Here is your current report:

---

{current_report_content}

---

If you'd like to make modifications, just let me know what you'd like to change (e.g., "use PostgreSQL instead of MongoDB" or "add Redis for caching")."""
                    else:
                        llm_response = "There are no pending changes to apply. Your report is up to date.\n\nIf you'd like to make modifications, just let me know what you'd like to change."
                except Exception as e:
                    logger.warning(f"Error getting current report: {str(e)}")
                    llm_response = "There are no pending changes to apply. Your report is up to date.\n\nIf you'd like to make modifications, just let me know what you'd like to change."
            else:
                # Check for conflicts before regenerating
                conflicts = detect_conflicts(pending_changes)

                if conflicts:
                    # Can't regenerate with conflicts
                    llm_response = await generate_conflict_resolution(
                        conflicts=conflicts,
                        all_pending_changes=pending_changes
                    )
                    action = "conflict_detected"
                else:
                    # Generate regeneration plan
                    try:
                        regen_plan = await generate_regeneration_plan(
                            original_report_summary=report_summary.summary_report if hasattr(report_summary, 'summary_report') else report_summary,
                            pending_changes=pending_changes,
                            conversation_context=conversation_context
                        )
                        logger.info(f"Generated regeneration plan: {regen_plan}")

                        sections_to_update = regen_plan.get("sections_to_regenerate", [])

                        # Phase 2: Actually regenerate the report
                        try:
                            # Get the original report content
                            original_report_content = report_summary.report_content if hasattr(report_summary, 'report_content') else None

                            if not original_report_content:
                                raise ValueError("Original report content not found")

                            logger.info(f"Starting section regeneration for chat_history_id: {chat_context['chat_history_id']}")

                            # Regenerate affected sections
                            regenerated_report = await regenerate_report_sections(
                                original_report=original_report_content,
                                regeneration_plan=regen_plan,
                                pending_changes=pending_changes
                            )

                            logger.info(f"Section regeneration completed, new report length: {len(regenerated_report)} chars")

                            # Create summary for the new report
                            new_summary = await main_report_summary(main_report=regenerated_report)
                            logger.info(f"Generated summary for regenerated report")

                            # Create new version
                            new_version_result = await create_new_report_version(
                                chat_history_id=chat_context["chat_history_id"],
                                user_id=current_user["regular_login_token"]["id"],
                                report_content=regenerated_report,
                                summary_report=new_summary,
                                changes_applied=pending_changes,
                                db=db
                            )

                            logger.info(f"Created new report version: {new_version_result['version_number']}")

                            # Clear pending changes after successful regeneration
                            await clear_pending_changes(chat_context["chat_history_id"], db)
                            logger.info(f"Cleared pending changes for chat_history_id: {chat_context['chat_history_id']}")

                            # Update vector DB with new report content
                            try:
                                new_chunks = await chunking.chunk_text(text=regenerated_report)
                                await vector_db.create_embeddings(
                                    texts=new_chunks,
                                    model=settings.EMBEDDING_MODEL,
                                    chat_history_id=chat_context["chat_history_id"]
                                )
                                logger.info(f"Updated vector DB with regenerated report")
                            except Exception as vec_error:
                                logger.warning(f"Failed to update vector DB: {str(vec_error)}")

                            # Generate success response with FULL report
                            llm_response = f"""**Report Regenerated Successfully** ✅

**Version:** {new_version_result['version_number']}
**Changes Applied:** {len(pending_changes)}

**Sections Updated:**
{chr(10).join(f"- {section.replace('_', ' ').title()}" for section in sections_to_update)}

**Changes Applied:**
{chr(10).join(f"- ✓ {c.get('user_request', 'Unknown change')}" for c in pending_changes)}

---

## Updated Report

{regenerated_report}

---

Your report has been updated with all the requested changes. You can:
- Ask me questions about the updated report
- Request more modifications
- View previous versions by asking "show version history"
- Rollback to a previous version if needed"""

                        except Exception as regen_error:
                            logger.error(f"Error during regeneration: {str(regen_error)}")
                            # Fall back to showing the plan if regeneration fails
                            llm_response = f"""**Report Regeneration Plan** 📋

I'll apply **{len(pending_changes)} pending changes** to your report.

**Sections to Update:**
{chr(10).join(f"- {section.replace('_', ' ').title()}" for section in sections_to_update)}

**Changes to Apply:**
{chr(10).join(f"- {c.get('user_request', 'Unknown change')}" for c in pending_changes)}

**Estimated Impact:** {regen_plan.get("estimated_impact", "medium").title()}

---

⚠️ **Error:** Regeneration encountered an issue: {str(regen_error)}

Your changes have been saved. Please try again or contact support if the issue persists."""

                    except Exception as e:
                        logger.error(f"Error generating regeneration plan: {str(e)}")
                        llm_response = f"I have {len(pending_changes)} pending changes ready to apply, but encountered an error creating the regeneration plan. Please try again."

        # Handle vector store retrieval
        elif action == "retrieve_from_vectorstore":
            try:
                vector_results = await vector_db.retrieve_similar_embeddings(
                    query_text=user_message,
                    chat_history_id=chat_context["chat_history_id"],
                    model=settings.EMBEDDING_MODEL,
                    top_k=5
                )
                # Extract documents from results
                if vector_results and "documents" in vector_results:
                    retrieved_context = "\n\n".join(vector_results["documents"][0]) if vector_results["documents"] else "No relevant content found"
                logger.info(f"Retrieved {len(vector_results.get('documents', [[]])[0])} chunks from vector DB")
            except Exception as e:
                logger.warning(f"Vector DB retrieval failed: {str(e)}, proceeding without retrieved context")
                retrieved_context = "Vector retrieval unavailable"

            # Generate response with retrieved context
            try:
                llm_response = await generate_action_response(
                    report_summary=report_summary.summary_report if hasattr(report_summary, 'summary_report') else report_summary,
                    conversation_context=conversation_context,
                    user_message=user_message,
                    action=action,
                    action_reason=action_reason,
                    retrieved_context=retrieved_context
                )
            except Exception as e:
                logger.error(f"Error generating response: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Error generating response: {str(e)}")

        # Handle all other actions (general_discussion, answer_question, improve_report, etc.)
        else:
            # Check if user is asking to see the full report
            show_report_keywords = ["show full report", "show the report", "show me the report",
                                   "display report", "view report", "see the report", "full report",
                                   "show report", "give me the report", "show updated report",
                                   "show current report", "show latest report"]
            user_message_lower = user_message.lower()

            is_show_report_request = any(keyword in user_message_lower for keyword in show_report_keywords)

            if is_show_report_request:
                # User wants to see the full report
                try:
                    current_report_content = report_summary.report_content if hasattr(report_summary, 'report_content') else None
                    current_version = report_summary.version_number if hasattr(report_summary, 'version_number') else 1

                    if current_report_content:
                        llm_response = f"""**Current Report (Version {current_version})** 📄

---

{current_report_content}

---

*This is the complete current version of your report. You can:*
- *Ask me to modify specific sections*
- *Request technology changes*
- *View version history*
- *Rollback to a previous version*"""
                    else:
                        llm_response = "I couldn't retrieve the full report content. Please try refreshing or contact support."
                except Exception as e:
                    logger.error(f"Error retrieving full report: {str(e)}")
                    llm_response = "I encountered an error retrieving the report. Please try again."
            else:
                # 7. Generate response based on action
                try:
                    llm_response = await generate_action_response(
                        report_summary=report_summary.summary_report if hasattr(report_summary, 'summary_report') else report_summary,
                        conversation_context=conversation_context,
                        user_message=user_message,
                        action=action,
                        action_reason=action_reason,
                        retrieved_context=retrieved_context
                    )
                    logger.info(f"Generated response for action: {action}")
                except Exception as e:
                    logger.error(f"Error generating response: {str(e)}")
                    raise HTTPException(status_code=500, detail=f"Error generating response: {str(e)}")

        # 8. Create new assistant message
        new_assistant_message = {
            "role": "assistant",
            "content": llm_response,
            "timestamp": datetime.now().isoformat(),
            "selected": True  # New AI responses are selected by default
        }

        # Append to full message list
        chat_context["message"].append(new_assistant_message)

        # 9. Save full conversation to chat_history
        try:
            await save_chat_history(chat=chat_context, db=db)
            logger.info(f"Saved full conversation to chat_history")
        except Exception as e:
            logger.error(f"Error saving chat history: {str(e)}")
            # Don't fail the request if save fails, just log it

        # 10. Save selected-only messages to selected_chat (for data collection)
        try:
            selected_only_data = {
                "chat_history_id": chat_context["chat_history_id"],
                "user_id": chat_context["user_id"],
                "document_id": chat_context["document_id"],
                "message": [msg for msg in chat_context["message"] if msg.get("selected", False)],
                "title": chat_context.get("title")
            }
            await save_chat_with_doc(chat_context=selected_only_data, db=db)
            logger.info(f"Saved selected messages to selected_chat ({len(selected_only_data['message'])} messages)")
        except Exception as e:
            logger.error(f"Error saving selected chat: {str(e)}")
            # Don't fail the request if save fails, just log it

        # 11. Return response with metadata
        response_data = {
            "message": llm_response,
            "action": action,
            "action_reason": action_reason
        }

        # Include pending changes info if available
        if pending_changes_info:
            response_data["pending_changes"] = pending_changes_info

        return response_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in chat-with-docs-v2: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


# ============================================================
# PENDING CHANGES MANAGEMENT ENDPOINTS
# ============================================================

@router.get('/pending-changes/{chat_history_id}')
async def get_pending_changes_endpoint(
    chat_history_id: str,
    current_user=Depends(token_validator),
    db: Session = Depends(get_db)
):
    """
    Get all pending changes for a chat/report.

    Returns:
        - List of pending changes
        - Conflict detection results
        - Affected sections summary
    """
    try:
        summary = await get_pending_changes_summary(chat_history_id, db)
        return summary
    except Exception as e:
        logger.error(f"Error getting pending changes: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting pending changes: {str(e)}")


@router.delete('/pending-changes/{chat_history_id}/{change_id}')
async def remove_pending_change_endpoint(
    chat_history_id: str,
    change_id: str,
    current_user=Depends(token_validator),
    db: Session = Depends(get_db)
):
    """
    Remove a specific pending change.
    Used for conflict resolution or when user wants to discard a change.

    Args:
        chat_history_id: The chat history ID
        change_id: The change ID to remove (e.g., "CHG-001")
    """
    try:
        result = await remove_pending_change(chat_history_id, change_id, db)
        logger.info(f"Removed pending change {change_id} for chat_history_id: {chat_history_id}")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing pending change: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error removing pending change: {str(e)}")


@router.delete('/pending-changes/{chat_history_id}')
async def clear_all_pending_changes_endpoint(
    chat_history_id: str,
    current_user=Depends(token_validator),
    db: Session = Depends(get_db)
):
    """
    Clear all pending changes for a chat/report.
    Use with caution - this discards all tracked changes.
    """
    try:
        result = await clear_pending_changes(chat_history_id, db)
        logger.info(f"Cleared all pending changes for chat_history_id: {chat_history_id}")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error clearing pending changes: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error clearing pending changes: {str(e)}")


# ============================================================
# REPORT VERSION MANAGEMENT ENDPOINTS (Phase 2)
# ============================================================

@router.get('/report-versions/{chat_history_id}')
async def get_version_history(
    chat_history_id: str,
    current_user=Depends(token_validator),
    db: Session = Depends(get_db)
):
    """
    Get all report versions for a chat history.

    Returns a list of versions with metadata (without full content for efficiency).
    """
    try:
        versions = await get_all_report_versions(chat_history_id, db)
        logger.info(f"Retrieved {len(versions)} versions for chat_history_id: {chat_history_id}")
        return {
            "chat_history_id": chat_history_id,
            "total_versions": len(versions),
            "versions": versions
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving version history: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error retrieving version history: {str(e)}")


@router.get('/report-versions/{chat_history_id}/{version_number}')
async def get_specific_version(
    chat_history_id: str,
    version_number: int,
    current_user=Depends(token_validator),
    db: Session = Depends(get_db)
):
    """
    Get a specific report version by version number.

    Returns the full report content and summary for the specified version.
    """
    try:
        version = await get_report_version_by_number(chat_history_id, version_number, db)
        logger.info(f"Retrieved version {version_number} for chat_history_id: {chat_history_id}")
        return version
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving version {version_number}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error retrieving version: {str(e)}")


@router.post('/report-versions/{chat_history_id}/rollback/{version_number}')
async def rollback_to_previous_version(
    chat_history_id: str,
    version_number: int,
    current_user=Depends(token_validator),
    db: Session = Depends(get_db)
):
    """
    Rollback to a previous report version.

    This creates a NEW version with the content from the target version,
    preserving the full history. Does not delete any versions.
    """
    try:
        result = await rollback_to_version(
            chat_history_id=chat_history_id,
            user_id=current_user["regular_login_token"]["id"],
            target_version_number=version_number,
            db=db
        )
        logger.info(f"Rolled back to version {version_number} for chat_history_id: {chat_history_id}")

        # Update vector DB with rolled back content
        try:
            rolled_back_version = await get_report_version_by_number(chat_history_id, result["new_version_number"], db)
            new_chunks = await chunking.chunk_text(text=rolled_back_version["report_content"])
            await vector_db.create_embeddings(
                texts=new_chunks,
                model=settings.EMBEDDING_MODEL,
                chat_history_id=chat_history_id
            )
            logger.info(f"Updated vector DB after rollback")
        except Exception as vec_error:
            logger.warning(f"Failed to update vector DB after rollback: {str(vec_error)}")

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error rolling back to version {version_number}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error rolling back: {str(e)}")


@router.get('/report-versions/{chat_history_id}/diff')
async def compare_versions(
    chat_history_id: str,
    version_a: int,
    version_b: int,
    current_user=Depends(token_validator),
    db: Session = Depends(get_db)
):
    """
    Compare two report versions and get diff statistics.

    Query params:
        version_a: First version number
        version_b: Second version number

    Returns diff statistics and summary comparison.
    """
    try:
        diff = await get_report_diff(chat_history_id, version_a, version_b, db)
        logger.info(f"Computed diff between versions {version_a} and {version_b} for chat_history_id: {chat_history_id}")
        return diff
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error computing diff: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error computing diff: {str(e)}")

