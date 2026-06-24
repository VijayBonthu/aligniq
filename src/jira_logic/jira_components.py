import requests
from utils.logger import logger
from fastapi import HTTPException, status, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer



async def get_jira_user_info(jira_access_token:str):
        """Get Jira user information using access token"""
        try:
            headers = {
                "Authorization": f"Bearer {jira_access_token}",
                "Accept": "application/json"
            }
            logger.info(f"creating header for Jira: {headers}")
            
            # Get user info from Atlassian
            response = requests.get(
                "https://api.atlassian.com/me",
                headers=headers
            )
            
            logger.info(f"User info response status: {response.status_code}")
            logger.info(f"User info response: {response.text}")
            
            if response.status_code != 200:
                raise Exception(f"Failed to get user info: {response.text}")
                
            user_info = response.json()
            return {
                "account_id": user_info.get("account_id"),
                "email": user_info.get("email"),
                "name": user_info.get("name"),
                "picture": user_info.get("picture"),
                "account_type": user_info.get("account_type")
            }
            
        except Exception as e:
            logger.error(f"Failed to get user info: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to get user info: {str(e)}"
            )


async def get_valid_jira_access_token(user_id: str, db) -> str:
    """Return a currently-valid Atlassian access token for the user, refreshing it in
    place (via the stored refresh token) when it's expired or within 60s of expiry.

    Raises 401 if Jira isn't connected or the refresh token is no longer accepted —
    the caller surfaces that as "reconnect Jira". This is the single source of truth
    used by every /jira/* endpoint and the push_to_jira chat tool, so no Jira token
    ever lives in the browser."""
    # Lazy imports avoid any module-load ordering issues between this domain module,
    # database_scripts (models) and oauth (config).
    import models
    from database_scripts import get_jira_credentials, save_jira_credentials, delete_jira_credentials
    from oauth import JiraOAuth
    from utils.crypto import decrypt_secret
    from datetime import datetime, timezone, timedelta

    def _expired(exp) -> bool:
        if exp is None:
            return False  # no recorded expiry → assume usable; Jira 401 would force reconnect
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return (exp - timedelta(seconds=60)) <= datetime.now(timezone.utc)

    cred = get_jira_credentials(user_id, db)
    if not cred:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Jira not connected")

    # Fast path: token still valid — return it without taking a lock.
    if not _expired(cred.expires_at):
        return decrypt_secret(cred.access_token)

    # Refresh path. Serialize per-user with a row lock so concurrent expired requests don't
    # each refresh — Atlassian rotates the refresh token, so a second refresh with the now-stale
    # token would fail. Re-check expiry after acquiring the lock (double-checked locking).
    locked = (
        db.query(models.JiraCredential)
        .filter(models.JiraCredential.user_id == user_id)
        .with_for_update()
        .first()
    )
    if not locked:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Jira not connected")
    if not _expired(locked.expires_at):
        # A sibling request refreshed while we waited on the lock.
        token = decrypt_secret(locked.access_token)
        db.commit()  # release the lock
        return token

    current_refresh = decrypt_secret(locked.refresh_token)
    if not current_refresh:
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Jira session expired — reconnect Jira")

    try:
        token_response = await JiraOAuth().refresh_access_token(current_refresh)
    except HTTPException as e:
        if e.status_code == status.HTTP_401_UNAUTHORIZED:
            # Permanent (revoked/expired refresh token): self-heal so the UI offers reconnect.
            delete_jira_credentials(user_id, db)  # commits + releases the lock
            raise
        db.rollback()  # transient (502): keep the row, release the lock, let the caller retry
        raise

    access_token = token_response["access_token"]
    expires_in = int(token_response.get("expires_in", 3600))
    save_jira_credentials(
        user_id,
        access_token=access_token,
        # Atlassian rotates refresh tokens — persist the new one (fall back to the current).
        refresh_token=token_response.get("refresh_token", current_refresh),
        scope=token_response.get("scope", locked.scope),
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
        db=db,  # save_jira_credentials commits → releases the lock
    )
    return access_token