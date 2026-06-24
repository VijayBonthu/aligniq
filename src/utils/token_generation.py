from jose import jwt, JWTError
from datetime import datetime, timedelta, timezone
from config import settings
from fastapi import status, HTTPException, Security, Request, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from passlib.context import CryptContext
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

    
    # logger.info(f"request headers: {request.headers}")
    # logger.info(f"token: {token}")
    jira_token = request.headers.get('Jira_Authorization')
    
    if jira_token:
        if jira_token.startswith("Bearer"):
            jira_token = jira_token.split(" ")[1]
        # logger.info(f"data got from the request Regular token: {token.credentials}")
        regular_token_details = await validate_app_user(token = token.credentials)
        # logger.info(f"regular token details: {regular_token_details}")
        # logger.info(f"data got from the request jira token: {request.headers.get('Jira_Authorization')}")
        jira_token_details = await validate_app_user(token = jira_token)
        # logger.info(f"jira token details: {jira_token_details}")
        # logger.info(f"regular_login_token: {regular_token_details}, jira_token: {jira_token_details}")
        return {"regular_login_token": regular_token_details, "jira_token": jira_token_details}
    regular_token = await validate_app_user(token = token.credentials)
    return {"regular_login_token": regular_token}

async def require_verified_email(current: dict = Depends(token_validator)) -> dict:
    """Like token_validator, but rejects users whose email isn't verified. SSO logins are
    provider-verified (verified_email=True) so this only blocks unverified Local accounts.
    Applied to compute-spending + projects endpoints so an unverified account (incl. one
    on a fake domain that never received the link) can't use the app. Returns the same
    shape as token_validator, so handlers can swap the dependency unchanged."""
    tok = current.get("regular_login_token") or {}
    if tok.get("verified_email") is False:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "Please verify your email to continue.", "code": "EMAIL_NOT_VERIFIED"},
        )
    return current


async def require_staff(current: dict = Depends(token_validator), db: Session = Depends(models.get_db)) -> dict:
    """Platform-admin gate for the /admin ops console. Authoritative: checks the DB
    `is_staff` flag rather than trusting a (possibly stale) token claim, so revoking
    staff takes effect immediately. JWT user id is the 'id' claim (see
    authentication._build_session_payload)."""
    tok = current.get("regular_login_token") or {}
    user_id = tok.get("id")
    user = db.query(models.User).filter(models.User.user_id == user_id).first() if user_id else None
    if not user or not getattr(user, "is_staff", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "Staff access required.", "code": "NOT_STAFF"},
        )
    return current

def hash_passwords(password:str):
    return pwd_context.hash(password)

def verify_password(password:str, hashed_password:str):
    return pwd_context.verify(password,hashed_password)

def _password_reset_bind(password_hash: str) -> str:
    """Short fingerprint of the user's CURRENT password hash, salted with the app
    secret. Embedded in the reset token so a link stops working the moment the
    password changes — i.e. single-use — without needing a reset-token table."""
    return hashlib.sha256((password_hash + settings.SECRET_KEY_J).encode()).hexdigest()[:32]

def create_password_reset_token(user_id: str, password_hash: str) -> str:
    """Short-lived (15 min), hash-bound JWT used as the password-reset link token."""
    payload = {
        "sub": user_id,
        "purpose": "pw_reset",
        "pwb": _password_reset_bind(password_hash),
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
    }
    return jwt.encode(payload, settings.SECRET_KEY_J, algorithm=settings.ALGORITHM)

def verify_password_reset_token(token: str, password_hash: str) -> str:
    """Return the user_id if `token` is a valid, unused reset token for the user
    whose current password hash is `password_hash`; else raise HTTPException(400).
    Pure (no DB) so it's unit-testable; the caller resolves `password_hash`."""
    invalid = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="This reset link is invalid or has expired.",
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY_J, algorithms=[settings.ALGORITHM])
    except JWTError:
        raise invalid
    if payload.get("purpose") != "pw_reset" or not payload.get("sub"):
        raise invalid
    if payload.get("pwb") != _password_reset_bind(password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This reset link has already been used.",
        )
    return payload["sub"]

def create_email_verification_token(user_id: str) -> str:
    """Signed, 24h email-verification token. Not hash-bound (unlike password reset) —
    re-verifying an already-verified account is a harmless no-op, so expiry + purpose
    are enough."""
    payload = {
        "sub": user_id,
        "purpose": "email_verify",
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(hours=24),
    }
    return jwt.encode(payload, settings.SECRET_KEY_J, algorithm=settings.ALGORITHM)


def verify_email_verification_token(token: str) -> str:
    """Return the user_id for a valid email-verification token, else raise HTTP 400."""
    invalid = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="This verification link is invalid or has expired.",
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY_J, algorithms=[settings.ALGORITHM])
    except JWTError:
        raise invalid
    if payload.get("purpose") != "email_verify" or not payload.get("sub"):
        raise invalid
    return payload["sub"]


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
    logger.debug("Validating app user token")
    credential_exception = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Could not validate credentials", headers={"WWW-Authenticate": "Bearer"})
    try:
        # token = credentials.credentials
        token = token
        # logger.info(f"token: {token}")
        token_decoder = TokenDecoder()
        payload = await token_decoder.decode_oauth_token(token=token)
        # logger.info(f"payload: {payload}")
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
    


