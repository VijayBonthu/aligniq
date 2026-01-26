from config import settings
import boto3
from utils.logger import logger


def get_s3_client():
    try:
        return boto3.client(
            's3',
            endpoint_url = settings.S3_ENDPOINT_URL,
            aws_access_key_id = settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key = settings.AWS_SECRET_ACCESS_KEY,
            region_name = settings.AWS_REGION
        )
    except Exception as e:
        logger.error(f"error creating s3 client: {str(e)}")

def ensure_bucket_exists(s3_client, bucket_name):
    try:
        # Check if bucket exists first (MinIO-specific fix)
        s3_client.head_bucket(Bucket=bucket_name)
        logger.info(f"Bucket {bucket_name} exists in s3")
        return {"bucket_status":"exists"}
    except s3_client.exceptions.ClientError as e:
        error_code = e.response.get("Error", {}).get("Code")
        if error_code == "404":  # Bucket does NOT exist
            s3_client.create_bucket(
                Bucket=bucket_name,
                CreateBucketConfiguration={
                    "LocationConstraint": "us-east-1"  # Match your MinIO region
                }
            )
            logger.error(f"Bucket doesnt Exists so create a new bucket {bucket_name}")
        else:
            raise

def upload_document_s3(s3_client, file_obj, current_document_path, content_type, bucket_name):
    try:
        response = s3_client.upload_fileobj(
            file_obj,
            bucket_name,
            current_document_path,
            ExtraArgs={'ContentType': content_type}
        )
        return response
    except Exception as e:
        logger.error(f"something went wrong while uploading to s3: {str(e)}")
        raise 

def get_document_s3(s3_client):
    raise NotImplementedError


    
        

