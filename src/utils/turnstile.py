"""Cloudflare Turnstile verification — a free, privacy-friendly bot challenge at signup.

The frontend renders the widget (VITE_TURNSTILE_SITE_KEY) and posts the resulting token;
we verify it server-side against Cloudflare's siteverify endpoint. If TURNSTILE_SECRET_KEY
is unset, verification is SKIPPED (returns True) so local dev runs without keys — same
best-effort fallback shape as utils/email. Cloudflare also publishes always-pass test keys
for local widgets (secret 1x0000000000000000000000000000000AA).
"""
from __future__ import annotations

import httpx

from config import settings
from utils.logger import logger

SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


async def verify_turnstile(token: str, remote_ip: str = None) -> bool:
    """Return True if the Turnstile token is valid (or if verification is disabled in dev).
    Never raises — a Cloudflare hiccup shouldn't 500 signup; we fail CLOSED on a present
    secret + bad/empty token, and OPEN only when no secret is configured."""
    if not settings.TURNSTILE_SECRET_KEY:
        logger.warning("TURNSTILE_SECRET_KEY unset — skipping captcha verification (dev mode).")
        return True
    if not token:
        return False
    data = {"secret": settings.TURNSTILE_SECRET_KEY, "response": token}
    if remote_ip:
        data["remoteip"] = remote_ip
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(SITEVERIFY_URL, data=data)
        body = resp.json()
        if not body.get("success"):
            logger.warning(f"Turnstile verification failed: {body.get('error-codes')}")
        return bool(body.get("success"))
    except Exception as e:  # noqa: BLE001 — treat network/parse errors as a failed challenge
        logger.error(f"Turnstile verification error: {e}")
        return False
