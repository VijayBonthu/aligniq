"""Thin transactional-email wrapper.

Currently backed by the Resend HTTP API (a single POST). Kept provider-agnostic
behind ``send_email(...)`` so swapping to SES / SendGrid later is a one-file
change. If ``RESEND_API_KEY`` is unset we don't fail — we log the email (link and
all) at WARNING so flows like password reset are testable locally without email
infrastructure. Callers treat the boolean return as best-effort and never leak
send status to the client (no account enumeration).
"""
from __future__ import annotations

import html as _html

import httpx

from config import settings
from utils.logger import logger

RESEND_ENDPOINT = "https://api.resend.com/emails"


async def send_email(to: str, subject: str, html: str) -> bool:
    """Send one HTML email. Returns True on success, False otherwise. Never raises
    (logs instead) so a transient email outage can't 500 an auth endpoint."""
    if not settings.RESEND_API_KEY:
        logger.warning(
            "RESEND_API_KEY unset — email NOT sent.\n  to=%s\n  subject=%s\n%s",
            to,
            subject,
            html,
        )
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                RESEND_ENDPOINT,
                headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
                json={
                    "from": settings.EMAIL_FROM,
                    "to": [to],
                    "subject": subject,
                    "html": html,
                },
            )
        if resp.status_code >= 400:
            logger.error("Resend send failed (%s): %s", resp.status_code, resp.text)
            return False
        return True
    except Exception as e:  # noqa: BLE001 — email is best-effort; never raise to the caller
        logger.error("Resend send error: %s", e)
        return False


def password_reset_email_html(name: str, reset_url: str) -> str:
    """On-brand HTML for the password-reset email. The raw URL is shown as a
    fallback for clients that strip the button."""
    safe_name = _html.escape(name or "there")
    safe_url = _html.escape(reset_url, quote=True)
    return f"""\
<!doctype html>
<html>
  <body style="margin:0;background:#0d0d11;font-family:Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#ece7dc;">
    <div style="max-width:480px;margin:0 auto;padding:40px 28px;">
      <div style="font-size:18px;font-weight:700;letter-spacing:-.02em;margin-bottom:28px;">
        Grounded<span style="color:#34a37b;">IQ</span>
      </div>
      <h1 style="font-size:22px;line-height:1.3;margin:0 0 12px;">Reset your password</h1>
      <p style="font-size:15px;line-height:1.6;color:#a39d8e;margin:0 0 24px;">
        Hi {safe_name}, we got a request to reset your GroundedIQ password.
        Click below to choose a new one. This link expires in 15 minutes and can
        be used once.
      </p>
      <a href="{safe_url}"
         style="display:inline-block;background:#34a37b;color:#ffffff;text-decoration:none;
                font-weight:600;font-size:15px;padding:12px 22px;border-radius:10px;">
        Reset password →
      </a>
      <p style="font-size:13px;line-height:1.6;color:#6e6a5e;margin:28px 0 0;">
        If the button doesn't work, paste this link into your browser:<br/>
        <a href="{safe_url}" style="color:#5fc69a;word-break:break-all;">{safe_url}</a>
      </p>
      <p style="font-size:13px;line-height:1.6;color:#6e6a5e;margin:24px 0 0;">
        Didn't request this? You can safely ignore this email — your password
        won't change.
      </p>
    </div>
  </body>
</html>"""
