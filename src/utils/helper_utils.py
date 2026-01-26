import asyncio
import aiofiles
import os
from fastapi import HTTPException, status
from utils.logger import logger
from utils.document_save import get_s3_client,ensure_bucket_exists, upload_document_s3
import mimetypes


async def save_file(file_path:str, file_content:str)->None:
    try:
        async with aiofiles.open(file_path, 'wb') as f:
            await f.write(file_content)
        logger.info(f"completed saving the file: {file_path}")
    except Exception as e:
        logger.error(f"Error saving file {file_path}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error saving file {file_path}")
    

async def upload_to_s3(file_path:str, file_uuid:str, document_name:str, file_extension:str, current_token_id:str, bucket_name:str, s3_folder:str) -> None:
    try:
        mime_type, _ = mimetypes.guess_type(file_path)
        s3 = get_s3_client()
        response = ensure_bucket_exists(s3_client=s3, bucket_name=bucket_name)
        if response.get("bucket_status") == "exists":
            with open(file_path, 'rb') as file_obj:
                s3_path = f"{s3_folder}/{current_token_id}/{document_name}_{file_uuid}.{file_extension}"
                upload_document_s3(s3_client=s3, file_obj=file_obj, current_document_path=s3_path, content_type=mime_type, bucket_name=bucket_name)
            logger.info(f"completed uploading the file to s3: {file_path} to bucket: {bucket_name} at path: {s3_path} for the user: {current_token_id}")    
    except Exception as e:
        logger.error(f"Error uploading file {file_path} to s3: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"error uploading file {file_path} to s3 bucker: {bucket_name} for the user: {current_token_id}")
