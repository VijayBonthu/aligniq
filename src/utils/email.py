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


async def send_email(
    to: str,
    subject: str,
    html: str,
    *,
    reply_to: str | None = None,
    attachments: list[dict] | None = None,
) -> bool:
    """Send one HTML email. Returns True on success, False otherwise. Never raises
    (logs instead) so a transient email outage can't 500 an auth endpoint.

    ``reply_to`` sets the Reply-To header (e.g. a support request replies to the
    requester). ``attachments`` is Resend's shape: ``[{"filename": str,
    "content": <base64 str>}]`` — used to attach user screenshots."""
    if not settings.RESEND_API_KEY:
        logger.warning(
            "RESEND_API_KEY unset — email NOT sent.\n  to=%s\n  reply_to=%s\n  attachments=%s\n  subject=%s\n%s",
            to,
            reply_to,
            [a.get("filename") for a in (attachments or [])],
            subject,
            html,
        )
        return False
    try:
        payload: dict = {
            "from": settings.EMAIL_FROM,
            "to": [to],
            "subject": subject,
            "html": html,
        }
        if reply_to:
            payload["reply_to"] = reply_to
        if attachments:
            payload["attachments"] = attachments
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                RESEND_ENDPOINT,
                headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
                json=payload,
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
      <a href="{safe_url}" target="_blank" rel="noopener noreferrer"
         style="display:inline-block;background:#34a37b;color:#ffffff;text-decoration:none;
                font-weight:600;font-size:15px;padding:12px 22px;border-radius:10px;">
        Reset password →
      </a>
      <p style="font-size:13px;line-height:1.6;color:#6e6a5e;margin:28px 0 0;">
        If the button doesn't work, paste this link into your browser:<br/>
        <a href="{safe_url}" target="_blank" rel="noopener noreferrer" style="color:#5fc69a;word-break:break-all;">{safe_url}</a>
      </p>
      <p style="font-size:13px;line-height:1.6;color:#6e6a5e;margin:24px 0 0;">
        Didn't request this? You can safely ignore this email — your password
        won't change.
      </p>
    </div>
  </body>
</html>"""


def email_verification_email_html(name: str, verify_url: str) -> str:
    """On-brand HTML for the signup email-verification message."""
    safe_name = _html.escape(name or "there")
    safe_url = _html.escape(verify_url, quote=True)
    return f"""\
<!doctype html>
<html>
  <body style="margin:0;background:#0d0d11;font-family:Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#ece7dc;">
    <div style="max-width:480px;margin:0 auto;padding:40px 28px;">
      <div style="font-size:18px;font-weight:700;letter-spacing:-.02em;margin-bottom:28px;">
        Grounded<span style="color:#34a37b;">IQ</span>
      </div>
      <h1 style="font-size:22px;line-height:1.3;margin:0 0 12px;">Confirm your email</h1>
      <p style="font-size:15px;line-height:1.6;color:#a39d8e;margin:0 0 24px;">
        Hi {safe_name}, welcome to GroundedIQ. Confirm this is your email to
        secure your account. This link expires in 24 hours.
      </p>
      <a href="{safe_url}" target="_blank" rel="noopener noreferrer"
         style="display:inline-block;background:#34a37b;color:#ffffff;text-decoration:none;
                font-weight:600;font-size:15px;padding:12px 22px;border-radius:10px;">
        Confirm email →
      </a>
      <p style="font-size:13px;line-height:1.6;color:#6e6a5e;margin:28px 0 0;">
        If the button doesn't work, paste this link into your browser:<br/>
        <a href="{safe_url}" target="_blank" rel="noopener noreferrer" style="color:#5fc69a;word-break:break-all;">{safe_url}</a>
      </p>
      <p style="font-size:13px;line-height:1.6;color:#6e6a5e;margin:24px 0 0;">
        Didn't create a GroundedIQ account? You can safely ignore this email.
      </p>
    </div>
  </body>
</html>"""


_GIQ_GREEN = "#34a37b"


def _branded_email_shell(
    *, sender_label: str, preheader: str, heading: str, body_html: str,
    cta_label: str, cta_url: str, accent: str = _GIQ_GREEN, footer_reason: str = "",
) -> str:
    """One professional, deliverability-friendly, GroundedIQ-branded HTML shell for
    all transactional client/firm emails. Table-based layout (renders across Outlook/
    Gmail/Apple Mail), a hidden preheader for the inbox preview, a clear single CTA,
    a plain-text fallback link, and a footer that ALWAYS carries the GroundedIQ mark +
    a 'why you got this' line (legitimacy → fewer spam flags). Content is pre-escaped
    by callers; `body_html` may contain safe markup we generate."""
    safe_cta_url = _html.escape(cta_url, quote=True)
    sender = _html.escape(sender_label or "GroundedIQ")
    reason = footer_reason or "You received this because a project team is working with you via GroundedIQ."
    return f"""\
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <meta name="color-scheme" content="light" />
    <title>{_html.escape(heading)}</title>
  </head>
  <body style="margin:0;padding:0;background:#eef2f9;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#111827;">
    <div style="display:none;max-height:0;overflow:hidden;opacity:0;color:#eef2f9;font-size:1px;line-height:1px;">{_html.escape(preheader)}</div>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#eef2f9;">
      <tr><td align="center" style="padding:32px 16px;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background:#ffffff;border-radius:14px;overflow:hidden;border:1px solid #e5e7eb;">
          <tr><td style="height:4px;background:{accent};font-size:0;line-height:0;">&nbsp;</td></tr>
          <tr><td style="padding:24px 32px 8px;">
            <span style="font-size:15px;font-weight:700;color:#111827;letter-spacing:-.01em;">{sender}</span>
          </td></tr>
          <tr><td style="padding:8px 32px 4px;">
            <h1 style="margin:0 0 12px;font-size:22px;line-height:1.3;color:#111827;font-weight:700;">{_html.escape(heading)}</h1>
            {body_html}
          </td></tr>
          <tr><td style="padding:8px 32px 28px;">
            <table role="presentation" cellpadding="0" cellspacing="0"><tr><td style="border-radius:10px;background:{accent};">
              <a href="{safe_cta_url}" target="_blank" rel="noopener noreferrer"
                 style="display:inline-block;padding:13px 26px;font-size:15px;font-weight:600;color:#ffffff;text-decoration:none;border-radius:10px;">{_html.escape(cta_label)}</a>
            </td></tr></table>
            <p style="font-size:13px;line-height:1.6;color:#9ca3af;margin:22px 0 0;">
              If the button doesn't work, copy and paste this link into your browser:<br/>
              <a href="{safe_cta_url}" target="_blank" rel="noopener noreferrer" style="color:{accent};word-break:break-all;">{safe_cta_url}</a>
            </p>
          </td></tr>
          <tr><td style="padding:16px 32px;background:#fbfcfe;border-top:1px solid #f1f5f9;">
            <p style="margin:0;font-size:12px;line-height:1.6;color:#9ca3af;">
              Sent with <strong style="color:#111827;">Grounded<span style="color:{_GIQ_GREEN};">IQ</span></strong> — scoping intelligence for software teams.<br/>
              {_html.escape(reason)}
            </p>
          </td></tr>
        </table>
      </td></tr>
    </table>
  </body>
</html>"""


# Default copy for the client questionnaire emails. Admins can override the text
# fields per-firm (firms.email_templates JSON); GroundedIQ branding + the shell are
# never overridable. `{firm}` is interpolated with the firm name.
DEFAULT_QUESTIONNAIRE_FIELDS = {
    "questionnaire_invite": {
        "subject": "A few questions about your project",
        "heading": "We need a few details about your project",
        "intro": "{firm} is scoping your project and needs a little more detail to get the estimate right. It only takes a few minutes — no account or login required.",
        "button_label": "Answer the questionnaire",
        "signoff": "",
    },
    "questionnaire_reminder": {
        "subject": "Reminder: your project questionnaire",
        "heading": "A quick reminder about your questionnaire",
        "intro": "Just a friendly reminder to finish the short questionnaire so we can scope your project accurately. Your previous answers are saved.",
        "button_label": "Finish the questionnaire",
        "signoff": "",
    },
}


def render_questionnaire_email(
    firm_name: str, link_url: str, *, fields: dict | None = None, message: str = "", is_reminder: bool = False,
) -> tuple[str, str]:
    """Render the client questionnaire invite/reminder → (subject, html). Merges the
    per-firm admin overrides (`fields`) over the defaults; empty/missing overrides fall
    back. GroundedIQ branding is always present (shell)."""
    key = "questionnaire_reminder" if is_reminder else "questionnaire_invite"
    base = dict(DEFAULT_QUESTIONNAIRE_FIELDS[key])
    for k, v in (fields or {}).items():
        if k in base and isinstance(v, str) and v.strip():
            base[k] = v

    firm = firm_name or "Our team"
    subject = base["subject"].replace("{firm}", firm)
    # heading is a plain-text param — the shell escapes it (don't double-escape here).
    heading = base["heading"].replace("{firm}", firm)
    # intro/message/signoff go into body_html (the shell does NOT escape that), so
    # escape them here.
    intro = _html.escape(base["intro"].replace("{firm}", firm)).replace("\n", "<br/>")
    safe_msg = _html.escape(message or "").replace("\n", "<br/>")
    signoff = _html.escape(base.get("signoff", "")).replace("\n", "<br/>")

    body = [f'<p style="font-size:15px;line-height:1.65;color:#4b5563;margin:0 0 18px;">{intro}</p>']
    if safe_msg:
        body.append(
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td '
            f'style="padding:12px 14px;background:#f3f4f6;border-radius:8px;font-size:14px;line-height:1.6;color:#374151;">'
            f'{safe_msg}</td></tr></table><div style="height:18px;"></div>'
        )
    if signoff:
        body.append(f'<p style="font-size:14px;line-height:1.6;color:#6b7280;margin:0 0 8px;">{signoff}</p>')

    html = _branded_email_shell(
        sender_label=firm,
        preheader=base["intro"].replace("{firm}", firm)[:120],
        heading=heading,
        body_html="\n".join(body),
        cta_label=base["button_label"],
        cta_url=link_url,
        accent="#4f46e5",
        footer_reason=f"You received this because {firm} is scoping a project with you.",
    )
    return subject, html


def questionnaire_invite_email_html(firm_name: str, link_url: str, message: str = "", is_reminder: bool = False) -> str:
    """Backward-compatible wrapper → HTML only (defaults, no per-firm overrides)."""
    return render_questionnaire_email(firm_name, link_url, message=message, is_reminder=is_reminder)[1]


def client_submission_notice_email_html(project_title: str, review_url: str, respondent: dict | None = None) -> str:
    """Firm-facing notice that the client submitted their answers — review now."""
    safe_title = _html.escape(project_title or "your project")
    who = ""
    if isinstance(respondent, dict) and respondent.get("name"):
        bits = _html.escape(respondent["name"])
        if respondent.get("designation"):
            bits += f", {_html.escape(respondent['designation'])}"
        if respondent.get("email"):
            bits += f" ({_html.escape(respondent['email'])})"
        who = f'<p style="font-size:14px;line-height:1.6;color:#a39d8e;margin:0 0 18px;">Completed by <strong>{bits}</strong>.</p>'
    body = (
        f'<p style="font-size:15px;line-height:1.65;color:#4b5563;margin:0 0 18px;">'
        f'Your client answered the questionnaire for <strong>{safe_title}</strong>. Review their answers, '
        f'accept or refine them, then run the readiness analysis to move toward the report.</p>'
        f'{who}'
    )
    return _branded_email_shell(
        sender_label="GroundedIQ",
        preheader=f"Your client submitted answers for {safe_title}.",
        heading="Your client submitted their answers",
        body_html=body,
        cta_label="Review the answers",
        cta_url=review_url,
        footer_reason="You received this because you're scoping this project in GroundedIQ.",
    )


# Human-readable labels for the support categories the form posts.
SUPPORT_CATEGORY_LABELS = {
    "bug": "Bug",
    "idea": "Feedback / idea",
    "question": "Question / help",
    "billing": "Billing",
}


def support_request_internal_html(
    *, ref_code: str, category: str, subject: str, message: str,
    user_name: str, user_email: str,
) -> str:
    """Team-facing notification for an in-app Help & Support request. Sent to
    SUPPORT_INBOX with reply_to = the requester, so a reply goes straight back to
    them. Plain, readable layout — the requester's screenshot rides along as an
    email attachment."""
    cat = _html.escape(SUPPORT_CATEGORY_LABELS.get(category, category or "—"))
    safe_ref = _html.escape(ref_code)
    safe_subject = _html.escape(subject or "(no subject)")
    safe_name = _html.escape(user_name or "—")
    safe_email = _html.escape(user_email or "—")
    safe_msg = _html.escape(message or "").replace("\n", "<br/>")

    def row(label: str, value: str) -> str:
        return (
            f'<tr><td style="padding:6px 0;font-size:13px;color:#6e6a5e;width:120px;'
            f'vertical-align:top;">{label}</td>'
            f'<td style="padding:6px 0;font-size:14px;color:#ece7dc;">{value}</td></tr>'
        )

    return f"""\
<!doctype html>
<html>
  <body style="margin:0;background:#0d0d11;font-family:Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#ece7dc;">
    <div style="max-width:560px;margin:0 auto;padding:36px 28px;">
      <div style="font-size:16px;font-weight:700;letter-spacing:-.02em;margin-bottom:8px;">
        Grounded<span style="color:#34a37b;">IQ</span> · Support
      </div>
      <h1 style="font-size:20px;line-height:1.3;margin:0 0 4px;">New support request</h1>
      <p style="font-size:13px;color:#6e6a5e;margin:0 0 22px;font-family:monospace;">{safe_ref}</p>
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
        {row("Category", f'<strong>{cat}</strong>')}
        {row("From", f'{safe_name} &lt;{safe_email}&gt;')}
        {row("Subject", safe_subject)}
      </table>
      <div style="margin:18px 0 0;padding:16px 18px;background:#1c1c25;border:1px solid rgba(220,210,180,.12);border-radius:10px;font-size:14px;line-height:1.6;color:#ece7dc;">
        {safe_msg}
      </div>
      <p style="font-size:13px;line-height:1.6;color:#6e6a5e;margin:22px 0 0;">
        Reply to this email to respond — it goes straight to {safe_email}. Any screenshot the user attached is included with this message.
      </p>
    </div>
  </body>
</html>"""


def support_confirmation_html(name: str, ref_code: str, subject: str) -> str:
    """User-facing 'we got your request' confirmation, in the same dark transactional
    style as the verification / password-reset emails."""
    safe_name = _html.escape(name or "there")
    safe_ref = _html.escape(ref_code)
    safe_subject = _html.escape(subject or "your request")
    return f"""\
<!doctype html>
<html>
  <body style="margin:0;background:#0d0d11;font-family:Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#ece7dc;">
    <div style="max-width:480px;margin:0 auto;padding:40px 28px;">
      <div style="font-size:18px;font-weight:700;letter-spacing:-.02em;margin-bottom:28px;">
        Grounded<span style="color:#34a37b;">IQ</span>
      </div>
      <h1 style="font-size:22px;line-height:1.3;margin:0 0 12px;">We got your request</h1>
      <p style="font-size:15px;line-height:1.6;color:#a39d8e;margin:0 0 16px;">
        Hi {safe_name}, thanks for reaching out about "<strong style="color:#ece7dc;">{safe_subject}</strong>".
        Our team will look into it and reply to this email address.
      </p>
      <p style="font-size:14px;line-height:1.6;color:#a39d8e;margin:0 0 24px;">
        Your reference number is
        <span style="font-family:monospace;color:#5fc69a;font-weight:600;">{safe_ref}</span> —
        mention it if you follow up.
      </p>
      <p style="font-size:13px;line-height:1.6;color:#6e6a5e;margin:24px 0 0;">
        You're receiving this because you submitted a support request in GroundedIQ.
      </p>
    </div>
  </body>
</html>"""
