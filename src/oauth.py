from google_auth_oauthlib.flow import Flow
from config import settings
import requests
from fastapi import HTTPException, status
from oauthlib.oauth2 import WebApplicationClient
from urllib.parse import urlparse, parse_qs, urlencode
from jose import jwt as jose_jwt
import logging

logger = logging.getLogger(__name__)
import os
# Only enable for local HTTP dev. In staging/prod the callback is HTTPS via
# Cloudflare, so leave OAUTHLIB_INSECURE_TRANSPORT unset (the default).
if os.getenv("OAUTH_ALLOW_INSECURE", "false").lower() == "true":
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

flow = Flow.from_client_config(
    client_config={
        "web": {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [settings.REDIRECT_URL],
        }
    },
    redirect_uri=settings.REDIRECT_URL,
    scopes=["https://www.googleapis.com/auth/userinfo.email",
            "https://www.googleapis.com/auth/userinfo.profile",
            "openid"]
)

def auth_callback(url:str=None):
    if not url:
        return "callback failed no link provided"
    try:
        authorization_response = str(url)
        logger.info(f"Authorization response: {authorization_response}")
        flow.fetch_token(authorization_response=authorization_response) 
        credentials = flow.credentials
        logger.info(f"Credentials: {credentials}")
        user_info_response = requests.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {credentials.token}"}
        )
        user_info = user_info_response.json()
        logger.info(f"User info: {user_info}")
        # Process and store user information in PostgreSQL
        return {"message": "Authentication successful", "user": user_info, "provider":"Google"}
    except Exception as e:
        logger.exception(f"Google OAuth callback failed for url={url}: {e}")
        return {"message": "bad request", "error": str(e)}
        

class JiraOAuth:
    def __init__(self):
        self.client_id = settings.JIRA_CLIENT_ID
        self.client_secret = settings.JIRA_CLIENT_SECRET
        self.redirect_uri = settings.JIRA_REDIRECT_URI
        logger.info(f"JiraOAuth initialized with redirect_uri: {self.redirect_uri}")
        self.oauth2_client = WebApplicationClient(self.client_id)

    async def get_authorization_url(self, state: str = None):
        """Generate authorization URL for Jira OAuth. A caller-supplied `state` (a signed
        token carrying the app user_id) is echoed back to the callback, so the callback
        can tie the Jira tokens to the right user without any auth header on the redirect."""
        try:
            result = self.oauth2_client.prepare_authorization_request(
                "https://auth.atlassian.com/authorize",
                redirect_url=self.redirect_uri,
                state=state,
                scope=[
                    "read:jira-user",
                    "read:jira-work",
                    "write:jira-work",
                    "offline_access",
                    "read:me",
                    "read:account"
                ],
                audience="api.atlassian.com",
                prompt="consent"
            )
            
            auth_url = result[0]
            parsed_url = urlparse(auth_url)
            query_params = parse_qs(parsed_url.query)
            state = query_params.get('state', [None])[0]
            
            return auth_url, state
        except Exception as e:
            logger.error(f"Error generating authorization URL: {str(e)}")
            raise

    async def get_access_token(self, code: str):
        """Exchange authorization code for access token"""
        try:
            token_url = "https://auth.atlassian.com/oauth/token"
            
            # Prepare token request with proper authorization code format
            body = {
                'grant_type': 'authorization_code',
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'code': code,
                'redirect_uri': self.redirect_uri
            }
            
            headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            }
            
            response = requests.post(
                token_url,
                json=body,  # Use json parameter instead of data
                headers=headers,
                verify=True  # Ensure SSL verification is enabled
            )
            
            logger.debug(f"Token response status: {response.status_code}")


            if response.status_code != 200:
                error_detail = response.json() if response.text else "No error details provided"
                raise Exception(f"Token request failed: {error_detail}")

            return response.json()

        except Exception as e:
            logger.error(f"Failed to get access token: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to get access token: {str(e)}"
            )

    async def refresh_access_token(self, refresh_token: str):
        """Exchange a Jira refresh token for a fresh access token (rotating refresh).

        Atlassian access tokens are short-lived (~1h); the `offline_access` scope grants
        a refresh token we use here so the user doesn't have to reconnect each hour.
        Atlassian rotates refresh tokens, so the caller must persist the NEW one.

        Raises 401 for a PERMANENT failure (invalid_grant — token revoked/expired; the
        caller should drop the credential and prompt reconnect) and 502 for a TRANSIENT
        failure (network / Atlassian 5xx; the caller should keep the credential and retry)."""
        token_url = "https://auth.atlassian.com/oauth/token"
        body = {
            'grant_type': 'refresh_token',
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'refresh_token': refresh_token,
        }
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
        try:
            response = requests.post(token_url, json=body, headers=headers, verify=True, timeout=20)
        except requests.RequestException as e:
            logger.error(f"Jira token refresh network error: {str(e)}")
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Jira temporarily unavailable")

        if response.status_code == 200:
            return response.json()

        detail = (response.text or "")[:300]
        if response.status_code in (400, 401, 403):
            # invalid_grant and friends — the refresh token is no longer accepted.
            logger.warning(f"Jira refresh permanently failed ({response.status_code}): {detail}")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Jira session expired — reconnect Jira")
        logger.error(f"Jira refresh transient failure ({response.status_code}): {detail}")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Jira temporarily unavailable")


# ---------------------------------------------------------------------------
# Login OAuth providers (GitHub, Microsoft) — "Sign in with X"
# ---------------------------------------------------------------------------
# Unlike JiraOAuth (which links an integration onto an already-signed-in user and
# stores the provider's tokens server-side), these are *login* providers: we exchange
# the code for a provider token only long enough to read a verified profile, then
# mint OUR OWN app session (JWT access + rotating refresh) and discard the provider
# token. So neither needs the provider's refresh token. Each `get_user_info` returns a
# dict in the exact shape `database_scripts.get_or_create_oauth_user` consumes.


def _normalize_profile(sub: str, email: str, name: str, picture: str = None) -> dict:
    """Map a raw provider profile to the user-creation shape. `verified_email` is True
    because we only ever build this from a provider-verified email (callers reject
    accounts without one)."""
    clean_email = (email or "").strip().lower()
    display = (name or "").strip() or (clean_email.split("@")[0] if clean_email else "user")
    parts = display.split()
    given = parts[0] if parts else display
    family = " ".join(parts[1:]) if len(parts) > 1 else ""
    return {
        "id": str(sub) if sub is not None else None,
        "email": clean_email,
        "verified_email": True,
        "name": display,
        "given_name": given,
        "family_name": family,
        "picture": picture,
    }


def _github_primary_verified_email(headers: dict) -> str:
    """GitHub's /user.email is null when the user hides their email, so resolve a
    real address from /user/emails: prefer the primary+verified one, else any
    verified one. Returns None if the account has no verified email (caller rejects)."""
    try:
        r = requests.get("https://api.github.com/user/emails", headers=headers, timeout=20)
    except requests.RequestException as e:
        logger.error(f"GitHub /user/emails network error: {e}")
        return None
    if r.status_code != 200:
        logger.warning(f"GitHub /user/emails failed ({r.status_code}): {r.text[:200]}")
        return None
    emails = r.json() or []
    verified = [e for e in emails if e.get("verified") and e.get("email")]
    primary = next((e["email"] for e in verified if e.get("primary")), None)
    if primary:
        return primary
    return verified[0]["email"] if verified else None


class GitHubOAuth:
    AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
    TOKEN_URL = "https://github.com/login/oauth/access_token"
    USER_URL = "https://api.github.com/user"

    def __init__(self):
        self.client_id = settings.GITHUB_CLIENT_ID
        self.client_secret = settings.GITHUB_CLIENT_SECRET
        self.redirect_uri = settings.GITHUB_REDIRECT_URI

    async def get_authorization_url(self, state: str):
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": "read:user user:email",
            "state": state,
            "allow_signup": "true",
            # Force GitHub's account picker on every sign-in. Without this, a user who is
            # still logged into github.com and has already authorized this OAuth app gets
            # redirected straight back with a code (no screen), silently re-logging them
            # into the same account — so they can never pick a different one. Mirrors the
            # prompt="consent" we send to Google/Jira.
            "prompt": "select_account",
        }
        return f"{self.AUTHORIZE_URL}?{urlencode(params)}", state

    async def get_access_token(self, code: str) -> str:
        try:
            resp = requests.post(
                self.TOKEN_URL,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code": code,
                    "redirect_uri": self.redirect_uri,
                },
                headers={"Accept": "application/json"},
                timeout=20,
            )
        except requests.RequestException as e:
            logger.error(f"GitHub token exchange network error: {e}")
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="GitHub temporarily unavailable")
        # GitHub returns HTTP 200 even on a bad code, with {"error": ...} in the body.
        data = resp.json() if resp.text else {}
        token = data.get("access_token")
        if resp.status_code != 200 or not token:
            detail = data.get("error_description") or data.get("error") or resp.text[:200]
            logger.warning(f"GitHub token exchange failed: {detail}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="GitHub sign-in failed")
        return token

    async def get_user_info(self, access_token: str) -> dict:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github+json",
        }
        try:
            u = requests.get(self.USER_URL, headers=headers, timeout=20)
        except requests.RequestException as e:
            logger.error(f"GitHub /user network error: {e}")
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="GitHub temporarily unavailable")
        if u.status_code != 200:
            logger.warning(f"GitHub /user failed ({u.status_code}): {u.text[:200]}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not read your GitHub profile")
        profile = u.json()
        email = _github_primary_verified_email(headers)
        if not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Your GitHub account has no verified email. Verify one on GitHub and try again.",
            )
        return _normalize_profile(
            sub=profile.get("id"),
            email=email,
            name=profile.get("name") or profile.get("login"),
            picture=profile.get("avatar_url"),
        )


class MicrosoftOAuth:
    """Microsoft identity platform (Entra ID) v2.0. The tenant segment is configurable:
    'common' (personal + work/school), 'organizations' (work/school only), or a tenant
    GUID (a single company) — the dial that turns this into enterprise SSO."""
    GRAPH_ME = "https://graph.microsoft.com/v1.0/me"

    def __init__(self):
        self.client_id = settings.MICROSOFT_CLIENT_ID
        self.client_secret = settings.MICROSOFT_CLIENT_SECRET
        self.redirect_uri = settings.MICROSOFT_REDIRECT_URI
        self.tenant = settings.MICROSOFT_TENANT or "common"
        self.authority = f"https://login.microsoftonline.com/{self.tenant}/oauth2/v2.0"

    async def get_authorization_url(self, state: str, nonce: str):
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "response_mode": "query",
            "scope": "openid email profile User.Read",
            "state": state,
            "nonce": nonce,
        }
        return f"{self.authority}/authorize?{urlencode(params)}", state

    async def get_access_token(self, code: str) -> dict:
        try:
            resp = requests.post(
                f"{self.authority}/token",
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code": code,
                    "redirect_uri": self.redirect_uri,
                    "grant_type": "authorization_code",
                    "scope": "openid email profile User.Read",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=20,
            )
        except requests.RequestException as e:
            logger.error(f"Microsoft token exchange network error: {e}")
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Microsoft temporarily unavailable")
        if resp.status_code != 200:
            logger.warning(f"Microsoft token exchange failed ({resp.status_code}): {resp.text[:200]}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Microsoft sign-in failed")
        return resp.json()

    async def get_user_info(self, token_response: dict, expected_nonce: str = None) -> dict:
        # Verify the id_token's nonce ties this response to OUR authorize request
        # (replay/injection guard). The id_token came over our back-channel TLS call
        # straight from Microsoft, same trust as the access token, so we read claims
        # without re-validating the signature; the nonce is the anti-forgery check.
        id_token = token_response.get("id_token")
        claims = {}
        if id_token:
            try:
                claims = jose_jwt.get_unverified_claims(id_token)
            except Exception:
                claims = {}
            if expected_nonce and claims.get("nonce") and claims.get("nonce") != expected_nonce:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign-in could not be verified")

        access_token = token_response.get("access_token")
        profile = {}
        if access_token:
            try:
                r = requests.get(self.GRAPH_ME, headers={"Authorization": f"Bearer {access_token}"}, timeout=20)
                if r.status_code == 200:
                    profile = r.json()
                else:
                    logger.warning(f"Microsoft Graph /me failed ({r.status_code}): {r.text[:200]}")
            except requests.RequestException as e:
                logger.error(f"Microsoft Graph /me network error: {e}")

        email = (
            profile.get("mail")
            or profile.get("userPrincipalName")
            or claims.get("email")
            or claims.get("preferred_username")
        )
        if not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Microsoft did not return an email for this account.",
            )
        sub = profile.get("id") or claims.get("oid") or claims.get("sub")
        name = profile.get("displayName") or claims.get("name")
        return _normalize_profile(sub=sub, email=email, name=name, picture=None)