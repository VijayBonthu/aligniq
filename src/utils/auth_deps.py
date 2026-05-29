"""
Shared FastAPI auth dependencies built on top of `token_validator`.

`token_validator` returns `{"regular_login_token": <jwt_payload>, ...}`. These
helpers unwrap that and apply role-based gates so router code stays clean.
"""

from typing import Optional

from fastapi import Depends, HTTPException, status

from utils.token_generation import token_validator


def _payload(current_token: dict) -> dict:
    """Pull the user JWT payload out of the token_validator wrapper dict."""
    if not current_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    payload = current_token.get("regular_login_token")
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token shape")
    return payload


def get_current_user_payload(current_token: dict = Depends(token_validator)) -> dict:
    """Just unwrap and return the JWT payload. Use when you need user info but no role gate."""
    return _payload(current_token)


def get_current_firm_id(current_token: dict = Depends(token_validator)) -> str:
    """
    Return the requesting user's firm_id. Raises 400 if the user has no firm yet
    (shouldn't happen after migration 019 backfill, but guards the case where a
    user was created before the migration and hasn't logged in since).
    """
    payload = _payload(current_token)
    firm_id: Optional[str] = payload.get("firm_id")
    if not firm_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No firm associated with this user. Log out and back in to refresh your session.",
        )
    return firm_id


def require_firm_admin(current_token: dict = Depends(token_validator)) -> dict:
    """
    Gate an endpoint to firm_admins of *some* firm. Returns the JWT payload so the
    handler can read firm_id without re-deserialising the token.
    """
    payload = _payload(current_token)
    if not payload.get("firm_id"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No firm associated with this user.",
        )
    if payload.get("firm_role") != "firm_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Firm admin role required.",
        )
    return payload
