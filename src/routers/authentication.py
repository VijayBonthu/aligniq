import os

from oauth import flow, auth_callback, JiraOAuth
from config import settings
from fastapi import Depends, HTTPException, Request, APIRouter, status, Header
from sqlalchemy.orm import Session
from models import get_db, User, LoginDetails
from database_scripts import create_user,UserCreationError, get_user_details, save_jira_credentials, delete_jira_credentials, get_jira_credentials
from utils.token_generation import create_token, verify_password, hash_passwords, create_password_reset_token, verify_password_reset_token, TokenDecoder, validate_app_user, validate_token_incoming_requests, token_validator, create_refresh_token, validate_refresh_token, revoke_refresh_token, rotate_refresh_token
from utils.email import send_email, password_reset_email_html
from p_model_type import Registration_login_password, login_details, PasswordResetRequest, PasswordResetConfirm
from pydantic import BaseModel
import logging
from jira_logic.jira_components import get_jira_user_info
from typing import Dict, Optional
from datetime import datetime, timezone, timedelta
from jose import jwt as jose_jwt
from fastapi.responses import JSONResponse, RedirectResponse, HTMLResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

class RefreshTokenRequest(BaseModel):
    refresh_token: str


logger = logging.getLogger(__name__)

router = APIRouter()

security = HTTPBearer()

auth_states = {}

# Fallback frontend origin for OAuth callback redirects when the SPA didn't pass its
# own origin. Set FRONTEND_URL via env (SSM in staging/prod).
FRONTEND_ORIGIN = settings.FRONTEND_URL or os.getenv("FRONTEND_URL", "http://localhost:5173")


def _make_oauth_state(user_id: str) -> str:
    """Signed, short-lived state that binds the OAuth round-trip to the initiating app
    user. Atlassian echoes it back to the callback, so we can store the Jira tokens for
    the right user without any auth header on the redirect. CSRF-safe — can't be forged
    without SECRET_KEY_J."""
    payload = {
        "uid": user_id,
        "purpose": "jira_oauth",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
    }
    return jose_jwt.encode(payload, settings.SECRET_KEY_J, algorithm=settings.ALGORITHM)


def _read_oauth_state(state: str) -> str:
    """Verify a state token and return the app user_id, or raise 401."""
    try:
        data = jose_jwt.decode(state, settings.SECRET_KEY_J, algorithms=[settings.ALGORITHM])
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired OAuth state")
    if data.get("purpose") != "jira_oauth" or not data.get("uid"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid OAuth state")
    return data["uid"]


def _jira_popup_html(ok: bool, message: str) -> HTMLResponse:
    """Minimal page shown in the OAuth popup. It carries NO token (those are stored
    server-side) — it just tells the user the result and tries to auto-close. The SPA
    detects success by polling GET /jira/status."""
    title = "Jira connected" if ok else "Jira sign-in failed"
    body = "You can close this window and return to GroundedIQ." if ok else message
    html = f"""<!doctype html><html><head><meta charset="utf-8"><title>{title}</title></head>
<body style="font-family:system-ui,Segoe UI,Roboto,sans-serif;background:#1b1b20;color:#e8ecf2;display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0">
<div style="text-align:center;max-width:360px;padding:24px">
<h2 style="margin:0 0 8px;font-size:18px">{title}</h2>
<p style="margin:0;color:#9aa3b2;font-size:14px;line-height:1.5">{body}</p>
</div>
<script>setTimeout(function(){{try{{window.close();}}catch(e){{}}}}, 1200);</script>
</body></html>"""
    return HTMLResponse(content=html)
@router.get("/auth/login")
async def login():
    result= flow.authorization_url(prompt="consent")

    auth_url = result[0] if isinstance(result, tuple) else result
    state = result[1] if isinstance(result, tuple) else None

    if state:
        auth_states[state] = True
    logger.debug("Generated Google OAuth authorization URL")
    return RedirectResponse(url=auth_url)

@router.get("/auth/callback", status_code=status.HTTP_200_OK)
async def callback(request: Request, db:Session=Depends(get_db)):
    # Extract the state from query parameters
    state = request.query_params.get("state")
    if not state or state not in auth_states:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Link already expired, Try to login in again")
    try:
        #Uses Google authentication to login
        response = auth_callback(url=request.url)
        if response.get("message") == "bad request":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Issue with your login, Please try again")
        user_data = response["user"]
    except UserCreationError as e:
        #add logging here to save it
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Something went wrong, it is not you, Please try after sometime")
    try:
        #create a record in DB if its the first time or get the details for jwt payload
        user = await create_user(user_data=user_data,provider=response['provider'], db=db)
        auth_states.pop(state,None)
        #add logging here to save it
    except UserCreationError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Something went wrong, it is not you, Please try after sometime") 
    
    payload= {
        "id": user.user_id,
        "oauth_id": user.oauth_id,
        "verified_email":user.verified_email,
        "picture": user.picture,
        "provider": user.provider,
        "email":user.email_address,
        "firm_id": user.firm_id,
        "firm_role": user.firm_role,
    }
    token = create_token(user_data=payload)
    refresh_token_val = create_refresh_token(user_id=user.user_id, db=db)

    html_content = f"""
    <html>
    <head><title>Authentication Complete</title></head>
    <body>
        <h2>Authentication Successful!</h2>
        <p>You can close this window and return to the application.</p>

        <script>
            if (window.opener) {{
                window.opener.postMessage(
                    {{
                        type: 'google_auth_success',
                        access_token: '{token}',
                        refresh_token: '{refresh_token_val}'
                    }},
                    '{FRONTEND_ORIGIN}'
                );

                setTimeout(() => window.close(), 3000);
            }}
        </script>
    </body>
    </html>
    """

    return HTMLResponse(content=html_content)

@router.post("/registration", status_code=status.HTTP_201_CREATED)
async def create_account(user_details:Registration_login_password, db:Session=Depends(get_db)):
    if not user_details:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Required details are not provided")
    try:
        user_details = user_details.__dict__
        username = user_details.get("username")
        role = user_details.get("role")
        user_details.update(
            {
                "id": None,
                "verified_email":False,
                "picture":None,
                "provider":"Local",
                "name":user_details["given_name"] + " " +user_details["family_name"]
            }
        )
        user = await create_user(user_data=user_details, provider="Local",db=db)
        if username or role:
            user.username = username
            user.role = role
            db.commit()
    except UserCreationError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Something went wrong, it is not you, Please try after sometime{e}")
    

    
    payload= {
        "id": user.user_id,
        "verified_email":user.verified_email,
        "picture": user.picture,
        "provider": user.provider,
        "email":user.email_address,
        "firm_id": user.firm_id,
        "firm_role": user.firm_role,
    }

    token = create_token(user_data=payload)
    refresh_token_val = create_refresh_token(user_id=user.user_id, db=db)

    return {"access_token": token, "refresh_token": refresh_token_val, "token_type": "bearer"}

@router.post("/login", status_code=status.HTTP_200_OK)
def log_into_account(login_details:login_details, db:Session=Depends(get_db)):
    if not login_details:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Please provide the details to login")
    try:
        user_details = get_user_details(email_address=login_details.email_address, db=db)
    except UserCreationError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record doesn't exists, please register to Login")

    checked_password = verify_password(password=login_details.password,hashed_password=user_details[6])
    if checked_password:
        # Fetch the full User row so we can include firm fields in the JWT (Bet 3).
        u = db.query(User).filter(User.user_id == user_details[1]).first()
        payload= {
            "id": user_details[1],
            "verified_email":user_details[4],
            "provider": user_details[5],
            "email":user_details[0],
            "firm_id": u.firm_id if u else None,
            "firm_role": u.firm_role if u else None,
        }
        token = create_token(user_data=payload)
        refresh_token_val = create_refresh_token(user_id=user_details[1], db=db)
        return {"access_token": token, "refresh_token": refresh_token_val, "token_type": "bearer"}
    else:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

@router.post("/auth/forgot-password", status_code=status.HTTP_200_OK)
async def forgot_password(body: PasswordResetRequest, db: Session = Depends(get_db)):
    """Email a single-use password-reset link. Always returns 200 (no account
    enumeration). The link carries a 15-min, hash-bound JWT that stops working the
    moment the password changes. Local accounts only — Google users sign in with
    Google, so there's nothing to reset here."""
    email = (body.email or "").strip().lower()
    if email:
        user = db.query(User).filter(
            User.email_address == email, User.provider == "Local"
        ).first()
        if user:
            login_row = db.query(LoginDetails).filter(
                LoginDetails.user_id == user.user_id
            ).first()
            if login_row:
                token = create_password_reset_token(user.user_id, login_row.hashed_password)
                reset_url = f"{FRONTEND_ORIGIN.rstrip('/')}/reset-password?token={token}"
                try:
                    await send_email(
                        to=user.email_address,
                        subject="Reset your GroundedIQ password",
                        html=password_reset_email_html(user.first_name or "there", reset_url),
                    )
                except Exception as e:
                    logger.error(f"Failed to send password reset email: {e}")
    return {"message": "If an account exists for that email, a reset link is on its way."}

@router.post("/auth/reset-password", status_code=status.HTTP_200_OK)
async def reset_password(body: PasswordResetConfirm, db: Session = Depends(get_db)):
    """Verify a reset token and set a new password. Single-use via the hash-bind in
    the token (see verify_password_reset_token)."""
    if not body.new_password or len(body.new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters.",
        )
    # Signature/expiry are checked again in verify_password_reset_token; here we just
    # read `sub` so we can load the current hash the token is bound to.
    try:
        unverified = jose_jwt.decode(
            body.token, settings.SECRET_KEY_J, algorithms=[settings.ALGORITHM]
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This reset link is invalid or has expired.",
        )
    user_id = unverified.get("sub")
    login_row = (
        db.query(LoginDetails).filter(LoginDetails.user_id == user_id).first()
        if user_id else None
    )
    if not login_row:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This reset link is invalid or has expired.",
        )
    # Full verify: signature, expiry, purpose, and single-use hash-bind.
    verify_password_reset_token(body.token, login_row.hashed_password)
    login_row.hashed_password = hash_passwords(body.new_password)
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to update password: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not update your password, please try again.",
        )
    return {"message": "Your password has been updated. You can now sign in."}

@router.get("/auth/jira/login")
async def jira_login(request: Request, current_user: dict = Depends(token_validator)):
    """Start the Jira OAuth flow. Authenticated via the app bearer so we can bind the
    flow to this user with a signed `state`; the callback uses it to store the Jira
    tokens server-side for the right user. Returns the Atlassian authorize URL."""
    try:
        user_id = current_user["regular_login_token"]["id"]
        state = _make_oauth_state(user_id)
        auth_url, _ = await JiraOAuth().get_authorization_url(state=state)
        return {"url": auth_url}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in jira_login: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.get("/auth/jira/callback")
async def jira_callback(request: Request, db: Session = Depends(get_db)):
    """Handle the Jira OAuth callback: verify the signed state → app user, exchange the
    code for Atlassian tokens, and persist them server-side for that user. Returns a
    minimal page that closes the popup — no token ever reaches the browser; the SPA
    learns it's connected by polling GET /jira/status."""
    state = request.query_params.get("state")
    code = request.query_params.get("code")
    error = request.query_params.get("error")

    if error:
        logger.error(f"Jira authorization error: {error}")
        return _jira_popup_html(False, f"Authorization failed: {error}")
    if not code or not state:
        return _jira_popup_html(False, "Missing code or state parameter")

    try:
        user_id = _read_oauth_state(state)
        token_response = await JiraOAuth().get_access_token(code)
        access_token = token_response["access_token"]
        user_info = await get_jira_user_info(access_token)
        expires_in = int(token_response.get("expires_in", 3600))
        save_jira_credentials(
            user_id,
            access_token=access_token,
            refresh_token=token_response.get("refresh_token"),
            account_id=user_info.get("account_id"),
            email=user_info.get("email"),
            scope=token_response.get("scope", ""),
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
            db=db,
        )
        logger.info(f"Jira connected for user {user_id} ({user_info.get('email')})")
        return _jira_popup_html(True, "Jira connected")
    except HTTPException as he:
        logger.error(f"Jira callback error: {he.detail}")
        return _jira_popup_html(False, str(he.detail))
    except Exception as e:
        logger.error(f"Jira callback error: {str(e)}")
        return _jira_popup_html(False, "Could not complete Jira sign-in")


@router.post("/auth/refresh", status_code=status.HTTP_200_OK)
async def refresh_access_token(request_body: RefreshTokenRequest, db: Session = Depends(get_db)):
    user_id = validate_refresh_token(request_body.refresh_token, db)
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    payload = {
        "id": user.user_id,
        "oauth_id": user.oauth_id,
        "verified_email": user.verified_email,
        "picture": user.picture,
        "provider": user.provider,
        "email": user.email_address,
        "firm_id": user.firm_id,
        "firm_role": user.firm_role,
    }
    new_access_token = create_token(user_data=payload)
    new_refresh_token = rotate_refresh_token(request_body.refresh_token, user_id, db)
    return {"access_token": new_access_token, "refresh_token": new_refresh_token, "token_type": "bearer"}

@router.post("/auth/logout", status_code=status.HTTP_200_OK)
async def logout(request_body: RefreshTokenRequest, db: Session = Depends(get_db)):
    try:
        revoke_refresh_token(request_body.refresh_token, db)
    except Exception:
        pass
    return {"message": "Logged out successfully"}

@router.get("/decode_token/{token}")
async def decode_token(token:str):
    token_decoder = TokenDecoder()
    return await token_decoder.decode_oauth_token(token=token)

@router.post("/validate_token")
async def validate_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    return await validate_app_user(credentials)


