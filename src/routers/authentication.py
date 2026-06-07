import os
import secrets

from oauth import flow, auth_callback, JiraOAuth, GitHubOAuth, MicrosoftOAuth
from config import settings
from fastapi import Depends, HTTPException, Request, Response, APIRouter, status, Header
from sqlalchemy.orm import Session
from models import get_db, User, LoginDetails
from database_scripts import create_user, get_or_create_oauth_user, record_identity, get_linked_identities, record_signup_event, UserCreationError, get_user_details, save_jira_credentials, delete_jira_credentials, get_jira_credentials
from utils.email_validation import is_disposable_email, is_valid_email_format, normalize_email
from utils.turnstile import verify_turnstile
from utils.rate_limit import get_client_ip, check_verification_resend, mark_verification_sent
from utils.token_generation import create_token, verify_password, hash_passwords, create_password_reset_token, verify_password_reset_token, create_email_verification_token, verify_email_verification_token, TokenDecoder, validate_app_user, validate_token_incoming_requests, token_validator, create_refresh_token, validate_refresh_token, revoke_refresh_token, rotate_refresh_token
from utils.email import send_email, password_reset_email_html, email_verification_email_html
from p_model_type import Registration_login_password, login_details, PasswordResetRequest, PasswordResetConfirm, EmailVerifyConfirm
import logging
from jira_logic.jira_components import get_jira_user_info
from typing import Dict, Optional
from datetime import datetime, timezone, timedelta
from jose import jwt as jose_jwt
from fastapi.responses import JSONResponse, RedirectResponse, HTMLResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

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


# ---------------------------------------------------------------------------
# Session issuance + httpOnly refresh-token cookie
# ---------------------------------------------------------------------------
# The long-lived refresh token lives ONLY in an httpOnly + Secure + SameSite cookie
# (JS can never read it — the high-value XSS mitigation). The short-lived access token
# is returned in the body / postMessage and kept in browser memory by the SPA. Path is
# scoped to /api/v1/auth so the cookie is only ever sent to the auth endpoints.
REFRESH_COOKIE_NAME = "refresh_token"
REFRESH_COOKIE_PATH = "/api/v1/auth"


def set_refresh_cookie(response: Response, raw_token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=raw_token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        domain=settings.COOKIE_DOMAIN,
        path=REFRESH_COOKIE_PATH,
    )


def clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        domain=settings.COOKIE_DOMAIN,
        path=REFRESH_COOKIE_PATH,
    )


def _build_session_payload(user: User, login_provider: str = None) -> dict:
    """The JWT claims carried in the access token. Single source of truth so the
    OAuth callbacks, local login, and /auth/refresh all mint identical sessions.
    `provider` is the account's stored origin; `login_provider` is how THIS session
    was authenticated (e.g. you may sign into a Local account via GitHub)."""
    return {
        "id": user.user_id,
        "oauth_id": getattr(user, "oauth_id", None),
        "verified_email": user.verified_email,
        "picture": user.picture,
        "provider": user.provider,
        "login_provider": login_provider or user.provider,
        "email": user.email_address,
        "firm_id": user.firm_id,
        "firm_role": user.firm_role,
    }


def _issue_session(user: User, db: Session, login_provider: str = None):
    """Return (access_token, raw_refresh_token) for a freshly authenticated user. The
    caller MUST put raw_refresh into an httpOnly cookie via set_refresh_cookie — it must
    never appear in a response body or postMessage."""
    access_token = create_token(user_data=_build_session_payload(user, login_provider))
    raw_refresh = create_refresh_token(user_id=user.user_id, db=db)
    return access_token, raw_refresh


async def _send_verification_email(user) -> None:
    """Best-effort signup email-verification send. Never raises (like forgot-password)
    so a transient email outage can't 500 signup; if RESEND_API_KEY is unset, utils/email
    logs the link instead of sending."""
    try:
        token = create_email_verification_token(user.user_id)
        # Point at the BACKEND GET endpoint, not the SPA: it verifies server-side and
        # renders plain HTML, so it works even when an email scanner / webview opens the
        # link in a JS-blocked sandboxed frame (where the React page would render blank).
        verify_url = f"{settings.BACKEND_URL.rstrip('/')}/api/v1/auth/verify-email?token={token}"
        await send_email(
            to=user.email_address,
            subject="Confirm your GroundedIQ email",
            html=email_verification_email_html(user.first_name or "there", verify_url),
        )
        # Arm the per-user cooldown + hourly count so the next send is throttled.
        await mark_verification_sent(user.user_id, settings.VERIFY_RESEND_COOLDOWN_SECONDS)
    except Exception as e:
        logger.error(f"Failed to send verification email: {e}")


# ---------------------------------------------------------------------------
# Social-login OAuth state + popup result pages (GitHub, Microsoft, Google)
# ---------------------------------------------------------------------------
def _make_login_state(provider: str):
    """Signed, short-lived CSRF state for a social-login round-trip. No user exists yet
    (unlike the Jira link flow), so it just proves the callback came from a flow WE
    started. Also carries a nonce we bind into the Microsoft id_token. Returns
    (state_token, nonce)."""
    nonce = secrets.token_urlsafe(16)
    payload = {
        "purpose": "oauth_login",
        "provider": provider,
        "nonce": nonce,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
    }
    return jose_jwt.encode(payload, settings.SECRET_KEY_J, algorithm=settings.ALGORITHM), nonce


def _read_login_state(state: str, provider: str) -> dict:
    """Verify a social-login state token (signature, expiry, purpose, provider). Raises
    401 on any mismatch. Returns the decoded claims (so the caller can read `nonce`)."""
    try:
        data = jose_jwt.decode(state, settings.SECRET_KEY_J, algorithms=[settings.ALGORITHM])
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired sign-in state")
    if data.get("purpose") != "oauth_login" or data.get("provider") != provider:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid sign-in state")
    return data


def _oauth_success_html_body(provider: str, access_token: str) -> str:
    """Popup page that hands the access token back to the SPA via postMessage. The
    refresh token is NOT here — it's already set as an httpOnly cookie on this response.
    `provider` drives the message type the frontend hook listens for
    (e.g. 'google_auth_success', 'github_auth_success')."""
    return f"""
    <html>
    <head><title>Authentication Complete</title></head>
    <body>
        <h2>Authentication Successful!</h2>
        <p>You can close this window and return to the application.</p>
        <script>
            if (window.opener) {{
                window.opener.postMessage(
                    {{
                        type: '{provider}_auth_success',
                        access_token: '{access_token}'
                    }},
                    '{FRONTEND_ORIGIN}'
                );
                setTimeout(() => window.close(), 1500);
            }}
        </script>
    </body>
    </html>
    """


def _oauth_error_html(provider: str, message: str) -> HTMLResponse:
    """Popup page for a failed social login. postMessages an error so the SPA can show a
    real message instead of the generic 'cancelled' it infers from a closed popup."""
    safe = (message or "Sign-in failed").replace("'", "").replace("\\", "").replace("<", "")[:200]
    html = f"""<!doctype html><html><head><meta charset="utf-8"><title>Sign-in failed</title></head>
<body style="font-family:system-ui,Segoe UI,Roboto,sans-serif;background:#1b1b20;color:#e8ecf2;display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0">
<div style="text-align:center;max-width:360px;padding:24px">
<h2 style="margin:0 0 8px;font-size:18px">Sign-in failed</h2>
<p style="margin:0;color:#9aa3b2;font-size:14px;line-height:1.5">{safe}</p>
</div>
<script>
if (window.opener) {{ window.opener.postMessage({{ type: '{provider}_auth_error', message: '{safe}' }}, '{FRONTEND_ORIGIN}'); }}
setTimeout(function(){{try{{window.close();}}catch(e){{}}}}, 2500);
</script>
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
        # Link-by-verified-email + identity tracking + disposable block + signup event,
        # same as GitHub/Microsoft (Google previously used create_user directly and missed all of it).
        user = await get_or_create_oauth_user(
            user_data, provider=response['provider'], db=db,
            ip=await get_client_ip(request), user_agent=request.headers.get("user-agent"),
        )
        auth_states.pop(state,None)
        #add logging here to save it
    except UserCreationError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Something went wrong, it is not you, Please try after sometime")
    
    access_token, raw_refresh = _issue_session(user, db, login_provider="Google")
    resp = HTMLResponse(content=_oauth_success_html_body("google", access_token))
    set_refresh_cookie(resp, raw_refresh)
    return resp

@router.post("/registration", status_code=status.HTTP_201_CREATED)
async def create_account(user_details:Registration_login_password, request: Request, response: Response, db:Session=Depends(get_db)):
    if not user_details:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Required details are not provided")

    # --- Anti-abuse gate (deterministic blocks, before we create anything) ---
    email = normalize_email(user_details.email)
    if not is_valid_email_format(email):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Please enter a valid email address.")
    if is_disposable_email(email):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Please sign up with a permanent (non-disposable) email address.")
    client_ip = await get_client_ip(request)
    if not await verify_turnstile(user_details.turnstile_token, client_ip):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Captcha verification failed. Please try again.")
    device_id = user_details.device_id

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
                "email": email,  # normalized (trimmed + lowercased)
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

    # Record the Local login identity and send a verification email. The account is
    # usable immediately (verified_email=False) but unverified until they click the link
    # — and an unverified account is taken over (its password revoked) if the real owner
    # later signs in via a provider-verified OAuth, which closes the pre-hijacking gap.
    record_identity(user.user_id, "Local", user.user_id, user.email_address, db)
    await _send_verification_email(user)
    record_signup_event(user, user.email_address, client_ip, device_id,
                        request.headers.get("user-agent"), "Local", db)

    access_token, raw_refresh = _issue_session(user, db, login_provider="Local")
    set_refresh_cookie(response, raw_refresh)
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/login", status_code=status.HTTP_200_OK)
def log_into_account(login_details:login_details, response: Response, db:Session=Depends(get_db)):
    if not login_details:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Please provide the details to login")
    try:
        user_details = get_user_details(email_address=login_details.email_address, db=db)
    except UserCreationError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record doesn't exists, please register to Login")

    checked_password = verify_password(password=login_details.password,hashed_password=user_details[6])
    if checked_password:
        # Fetch the full User row so the JWT carries firm fields (Bet 3) and the
        # session is minted identically to the OAuth paths (_build_session_payload).
        u = db.query(User).filter(User.user_id == user_details[1]).first()
        if not u:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        access_token, raw_refresh = _issue_session(u, db)
        set_refresh_cookie(response, raw_refresh)
        return {"access_token": access_token, "token_type": "bearer"}
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

def _verify_email_html(ok: bool, message: str) -> HTMLResponse:
    """Plain, JS-free result page for the email-verification GET link, so it renders even
    inside a sandboxed/JS-blocked email preview or link scanner (where the React SPA would
    show a blank page)."""
    title = "Email verified" if ok else "Verification failed"
    accent = "#34a37b" if ok else "#c0563f"
    login_url = f"{FRONTEND_ORIGIN.rstrip('/')}/login"
    html = f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>{title}</title></head>
<body style="margin:0;background:#0d0d11;font-family:Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#ece7dc;display:flex;min-height:100vh;align-items:center;justify-content:center">
<div style="max-width:440px;padding:40px 28px;text-align:center">
<div style="font-size:20px;font-weight:700;letter-spacing:-.02em;margin-bottom:24px">Grounded<span style="color:#34a37b">IQ</span></div>
<h1 style="font-size:24px;line-height:1.3;margin:0 0 12px;color:{accent}">{title}</h1>
<p style="font-size:15px;line-height:1.6;color:#a39d8e;margin:0 0 28px">{message}</p>
<a href="{login_url}" target="_blank" rel="noopener noreferrer" style="display:inline-block;background:#34a37b;color:#fff;text-decoration:none;font-weight:600;font-size:15px;padding:12px 24px;border-radius:10px">Continue to GroundedIQ &rarr;</a>
</div></body></html>"""
    return HTMLResponse(content=html, status_code=status.HTTP_200_OK)


@router.get("/auth/verify-email")
async def verify_email_link(request: Request, db: Session = Depends(get_db)):
    """The link we EMAIL — server-rendered, no JS. Verifies the token, marks the account
    verified (idempotent), and returns a plain HTML result page. Works in JS-blocked
    sandboxed frames (Safe Links, webview previews) that blank out the React page."""
    token = request.query_params.get("token", "")
    invalid_msg = "This verification link is invalid or has expired. Sign in to request a new one."
    try:
        user_id = verify_email_verification_token(token)
    except HTTPException:
        return _verify_email_html(False, invalid_msg)
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        return _verify_email_html(False, invalid_msg)
    if not user.verified_email:
        user.verified_email = True
        try:
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to mark email verified (GET) for {user_id}: {e}")
            return _verify_email_html(False, "We couldn't verify your email just now. Please open the link again.")
    return _verify_email_html(True, "Your email is verified. You can now sign in and start scoping.")

@router.post("/auth/verify-email", status_code=status.HTTP_200_OK)
async def verify_email(body: EmailVerifyConfirm, db: Session = Depends(get_db)):
    """Confirm a signup email-verification link → mark the account verified. Idempotent:
    re-clicking after verification just succeeds again."""
    user_id = verify_email_verification_token(body.token)
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This verification link is invalid or has expired.",
        )
    if not user.verified_email:
        user.verified_email = True
        try:
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to mark email verified for {user_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Could not verify your email, please try again.",
            )
    return {"message": "Your email is verified."}

@router.post("/auth/resend-verification", status_code=status.HTTP_200_OK)
async def resend_verification(current_user: dict = Depends(token_validator), db: Session = Depends(get_db)):
    """Re-send the verification email to the signed-in user (no-op if already verified).
    Throttled per user: a cooldown between sends + an hourly cap (429 if exceeded), so a
    client can't run up email cost by hammering 'resend'. `cooldown` is returned so the UI
    can show a countdown."""
    user_id = current_user["regular_login_token"]["id"]
    user = db.query(User).filter(User.user_id == user_id).first()
    if user and not user.verified_email:
        allowed, retry_after = await check_verification_resend(
            user_id, settings.VERIFY_RESEND_COOLDOWN_SECONDS, settings.VERIFY_RESEND_HOURLY_CAP)
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={"error": "Please wait before requesting another verification email.",
                        "retry_after": retry_after},
                headers={"Retry-After": str(retry_after)},
            )
        await _send_verification_email(user)
    return {"message": "If your email needs confirming, a new link is on its way.",
            "cooldown": settings.VERIFY_RESEND_COOLDOWN_SECONDS}

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


@router.get("/auth/github/login")
async def github_login():
    """Start 'Sign in with GitHub'. The SPA opens this in a popup; we redirect to
    GitHub's consent screen with a signed CSRF state."""
    state, _ = _make_login_state("github")
    auth_url, _ = await GitHubOAuth().get_authorization_url(state)
    return RedirectResponse(url=auth_url)


@router.get("/auth/github/callback")
async def github_callback(request: Request, db: Session = Depends(get_db)):
    """GitHub OAuth callback: verify state → exchange code → read a verified profile →
    link-or-create the user by verified email → mint our app session (access token via
    postMessage, refresh token as httpOnly cookie)."""
    error = request.query_params.get("error")
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    if error:
        return _oauth_error_html("github", request.query_params.get("error_description") or error)
    if not code or not state:
        return _oauth_error_html("github", "Missing code or state")
    try:
        _read_login_state(state, "github")
        gh = GitHubOAuth()
        access_token_gh = await gh.get_access_token(code)
        profile = await gh.get_user_info(access_token_gh)
        user = await get_or_create_oauth_user(
            profile, provider="GitHub", db=db,
            ip=await get_client_ip(request), user_agent=request.headers.get("user-agent"),
        )
        access_token, raw_refresh = _issue_session(user, db, login_provider="GitHub")
        resp = HTMLResponse(content=_oauth_success_html_body("github", access_token))
        set_refresh_cookie(resp, raw_refresh)
        return resp
    except HTTPException as he:
        return _oauth_error_html("github", str(he.detail))
    except Exception as e:
        logger.error(f"GitHub callback error: {e}")
        return _oauth_error_html("github", "Could not complete GitHub sign-in")


@router.get("/auth/microsoft/login")
async def microsoft_login():
    """Start 'Sign in with Microsoft' (Microsoft identity platform / Entra ID). The
    nonce is bound into the state and later checked against the id_token."""
    state, nonce = _make_login_state("microsoft")
    auth_url, _ = await MicrosoftOAuth().get_authorization_url(state, nonce)
    return RedirectResponse(url=auth_url)


@router.get("/auth/microsoft/callback")
async def microsoft_callback(request: Request, db: Session = Depends(get_db)):
    """Microsoft OAuth callback: verify state (+ id_token nonce) → read profile from
    Graph → link-or-create by verified email → mint our app session."""
    error = request.query_params.get("error")
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    if error:
        return _oauth_error_html("microsoft", request.query_params.get("error_description") or error)
    if not code or not state:
        return _oauth_error_html("microsoft", "Missing code or state")
    try:
        state_data = _read_login_state(state, "microsoft")
        ms = MicrosoftOAuth()
        token_response = await ms.get_access_token(code)
        profile = await ms.get_user_info(token_response, expected_nonce=state_data.get("nonce"))
        user = await get_or_create_oauth_user(
            profile, provider="Microsoft", db=db,
            ip=await get_client_ip(request), user_agent=request.headers.get("user-agent"),
        )
        access_token, raw_refresh = _issue_session(user, db, login_provider="Microsoft")
        resp = HTMLResponse(content=_oauth_success_html_body("microsoft", access_token))
        set_refresh_cookie(resp, raw_refresh)
        return resp
    except HTTPException as he:
        return _oauth_error_html("microsoft", str(he.detail))
    except Exception as e:
        logger.error(f"Microsoft callback error: {e}")
        return _oauth_error_html("microsoft", "Could not complete Microsoft sign-in")


@router.post("/auth/refresh", status_code=status.HTTP_200_OK)
async def refresh_access_token(request: Request, response: Response, db: Session = Depends(get_db)):
    """Silently re-mint the short-lived access token from the httpOnly refresh cookie.
    Returns ONLY the access token (the refresh token stays in its cookie). SameSite=lax
    blocks the cross-site POST a CSRF attack would need.

    We deliberately do NOT rotate the refresh token here. Rotating per-refresh self-revokes
    under concurrency — React StrictMode's double-mount, multiple tabs, or two requests
    refreshing at once would have one rotation revoke the cookie the other is still using,
    spuriously logging the user out. The refresh token remains httpOnly + Secure + SameSite,
    is revoked on logout, and expires on its own; only the access token is re-minted."""
    raw_refresh = request.cookies.get(REFRESH_COOKIE_NAME)
    if not raw_refresh:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No refresh token")
    user_id = validate_refresh_token(raw_refresh, db)
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    new_access_token = create_token(user_data=_build_session_payload(user))
    return {"access_token": new_access_token, "token_type": "bearer"}

@router.post("/auth/logout", status_code=status.HTTP_200_OK)
async def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    raw_refresh = request.cookies.get(REFRESH_COOKIE_NAME)
    if raw_refresh:
        try:
            revoke_refresh_token(raw_refresh, db)
        except Exception:
            pass
    clear_refresh_cookie(response)
    return {"message": "Logged out successfully"}

@router.get("/auth/identities", status_code=status.HTTP_200_OK)
async def list_identities(current_user: dict = Depends(token_validator), db: Session = Depends(get_db)):
    """Linked login methods (Google/GitHub/Microsoft/Local) for the signed-in user —
    backs a future Connected-accounts surface."""
    user_id = current_user["regular_login_token"]["id"]
    return {"identities": get_linked_identities(user_id, db)}

@router.get("/decode_token/{token}")
async def decode_token(token:str):
    token_decoder = TokenDecoder()
    return await token_decoder.decode_oauth_token(token=token)

@router.post("/validate_token")
async def validate_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    return await validate_app_user(credentials)


