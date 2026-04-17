from jose import jwt, JWTError
from datetime import datetime, timedelta, timezone
from config import settings
from fastapi import status, HTTPException,Security, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from passlib.context import CryptContext
import easyocr
from typing import Dict
import base64
import json
import secrets
import hashlib
from sqlalchemy.orm import Session
import models
from utils.logger import logger

UPLOADS_DIR = "uploads"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

def create_token(user_data:dict):
    try:
        to_encode = user_data.copy()
        to_encode.update({
            "iat":datetime.now(timezone.utc),
            "exp":datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        })
        return jwt.encode(
            to_encode,
            settings.SECRET_KEY_J,
            algorithm=settings.ALGORITHM)
    except JWTError as e:
        raise Exception(f"Failed to create token: {str(e)}")

def create_refresh_token(user_id: str, db: Session) -> str:
    raw_token = secrets.token_hex(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    refresh_token = models.RefreshToken(
        user_id=user_id,
        token_hash=token_hash,
        expires_at=expires_at
    )
    db.add(refresh_token)
    db.commit()
    return raw_token

def validate_refresh_token(raw_token: str, db: Session) -> str:
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    refresh_token = db.query(models.RefreshToken).filter(
        models.RefreshToken.token_hash == token_hash,
        models.RefreshToken.revoked == False
    ).first()
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    if refresh_token.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token expired")
    return refresh_token.user_id

def revoke_refresh_token(raw_token: str, db: Session):
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    refresh_token = db.query(models.RefreshToken).filter(
        models.RefreshToken.token_hash == token_hash
    ).first()
    if refresh_token:
        refresh_token.revoked = True
        db.commit()

def rotate_refresh_token(old_raw: str, user_id: str, db: Session) -> str:
    revoke_refresh_token(old_raw, db)
    return create_refresh_token(user_id, db)

async def validate_token(token:str, credential_exception):
    try:
        if not token:
            raise Exception(f"No token provided in the header")
    #change has been made in key for all auths if it doesnt work remove secrets from paramters and key and replace it with settings.SECRET_KEY_J
        payload = jwt.decode(
            token=token,
            key=settings.SECRET_KEY_J,
            algorithms=settings.ALGORITHM
            )
        
        exp = payload.get("exp")
        if not exp or datetime.fromtimestamp(exp, tz=timezone.utc)<datetime.now(timezone.utc):
            raise credential_exception
        return payload
    except JWTError:
        raise credential_exception

async def validate_token_incoming_requests(token:str):
    try:
        if not token:
            raise Exception(f"No token provided in the header")
    #change has been made in key for all auths if it doesnt work remove secrets from paramters and key and replace it with settings.SECRET_KEY_J
        payload = jwt.decode(
            token=token,
            key=settings.SECRET_KEY_J,
            algorithms=settings.ALGORITHM
            )
        exp = payload.get("exp")
        if not exp or datetime.fromtimestamp(exp, tz=timezone.utc)<datetime.now(timezone.utc):
            raise Exception(f"token expired")
        return payload
    except JWTError as e:
        raise Exception(f"failed to validate token: {str(e)}")
    
def get_current_user(token: HTTPAuthorizationCredentials = Security(security)):
    credential_exception = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Could not validate credentials", headers={"WWW-Authenticate": "Bearer"})
    return validate_token(token.credentials, credential_exception)

async def token_validator(request: Request,token: HTTPAuthorizationCredentials = Security(security)):

    
    logger.info(f"request headers: {request.headers}")
    logger.info(f"token: {token}")
    jira_token = request.headers.get('Jira_Authorization')
    
    if jira_token:
        if jira_token.startswith("Bearer"):
            jira_token = jira_token.split(" ")[1]
        logger.info(f"data got from the request Regular token: {token.credentials}")
        regular_token_details = await validate_app_user(token = token.credentials)
        logger.info(f"regular token details: {regular_token_details}")
        logger.info(f"data got from the request jira token: {request.headers.get('Jira_Authorization')}")
        jira_token_details = await validate_app_user(token = jira_token)
        logger.info(f"jira token details: {jira_token_details}")
        logger.info(f"regular_login_token: {regular_token_details}, jira_token: {jira_token_details}")
        return {"regular_login_token": regular_token_details, "jira_token": jira_token_details}
    regular_token = await validate_app_user(token = token.credentials)
    return {"regular_login_token": regular_token}

def hash_passwords(password:str):
    return pwd_context.hash(password)

def verify_password(password:str, hashed_password:str):
    return pwd_context.verify(password,hashed_password)

#extact text from images
def extract_text_from_image_easy(image_path) -> str:
    #add languages in config file
    reader = easyocr.Reader(settings.IMAGE_TEXT_LANGUAGE)
    #details 0 gives the text directly if you give 1 it will provide you with CI of those values and probably the postion of the word 
    results = reader.readtext(image_path, detail=0)
    extracted_text = " ".join(results)
    return extracted_text

def validate_jira_token(token: str):
    """Validate Jira-specific JWT token"""
    try:
        payload = jwt.decode(
            token=token,
            key=settings.SECRET_KEY_J,
            algorithms=settings.ALGORITHM
        )
        
        # Check if it's a Jira token
        if payload.get("provider") != "Jira":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Jira token"
            )
            
        # Check expiration
        exp = payload.get("exp")
        if not exp or datetime.fromtimestamp(exp, tz=timezone.utc) < datetime.now(timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Jira token has expired"
            )
            
        return payload
        
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid Jira token: {str(e)}"
        )
class TokenDecoder:
    @staticmethod
    async def decode_oauth_token(token: str):
        try:
            parts = token.split('.')
            if  len(parts) != 3:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token format")
            
            padded = parts[1] + '=' *(4-len(parts[1]) % 4)
            payload = base64.b64decode(padded)
            return json.loads(payload)
        except Exception as e:
            logger.error(f"Error decoding token: {str(e)}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token format")

async def validate_app_user(token:str):
    """Validate the app's JWT token"""
    print("inside validate app user")
    credential_exception = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Could not validate credentials", headers={"WWW-Authenticate": "Bearer"})
    try:
        # token = credentials.credentials
        token = token
        logger.info(f"token: {token}")
        token_decoder = TokenDecoder()
        payload = await token_decoder.decode_oauth_token(token=token)
        logger.info(f"payload: {payload}")
        # if payload['provider'] == "Jira":
        #     secret = await get_jira_certs_async()
        #     logger.info(f"secret_jira: {secret}")
        # elif payload['provider'] == "Google":
        #     secret = await get_google_certs_async()
        #     logger.info(f"secret_google: {secret}")
        # if payload['provider'] == "Local":
        #     secret = settings.SECRET_KEY_J
        #     logger.info(f"secret_local: {secret}")

        return await validate_token(token=token, credential_exception=credential_exception)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"error {str(e)}")
    


