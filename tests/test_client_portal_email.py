"""Client Readiness Portal email templates (WS-3 v2): the AlignIQ-branded shell,
per-firm override merge, the invite/reminder, and the firm submission notice."""

from src.utils.email import (
    password_reset_email_html,
    email_verification_email_html,
    support_confirmation_html,
    support_reply_html,
    questionnaire_invite_email_html,
    client_submission_notice_email_html,
    render_questionnaire_email,
    DEFAULT_QUESTIONNAIRE_FIELDS,
)


def _brand_present(html: str) -> bool:
    # The wordmark renders as Align<span>IQ</span>, so assert the parts + tagline,
    # and that the old product name is gone.
    return "Align" in html and ">IQ<" in html and "Sent with" in html and "Grounded" not in html


def test_invite_includes_firm_link_message_and_brand():
    html = questionnaire_invite_email_html("Acme Consulting", "https://app/q/abc123", message="Thanks for your time!")
    assert "Acme Consulting" in html       # sender + footer reason
    assert "https://app/q/abc123" in html  # CTA + fallback link
    assert "Thanks for your time!" in html
    assert "Answer the questionnaire" in html
    assert _brand_present(html)            # AlignIQ brand always present
    assert "reminder" not in html.lower()


def test_reminder_variant_and_brand():
    html = questionnaire_invite_email_html("Acme", "https://app/q/x", is_reminder=True)
    assert "reminder" in html.lower()
    assert _brand_present(html)


def test_escapes_html_in_message_and_firm():
    html = questionnaire_invite_email_html("<script>Evil</script>", "https://app/q/x", message="<b>hi</b>")
    assert "<script>Evil</script>" not in html
    assert "&lt;script&gt;" in html
    assert "<b>hi</b>" not in html


def test_no_message_omits_note_block():
    html = questionnaire_invite_email_html("Acme", "https://app/q/x")
    assert "background:#f3f4f6" not in html


def test_per_firm_override_merges_over_default_and_keeps_brand():
    subject, html = render_questionnaire_email(
        "Acme", "https://app/q/x",
        fields={"heading": "Tell us about your rollout", "subject": "Quick scoping questions", "intro": ""},
    )
    assert subject == "Quick scoping questions"           # subject override wins
    assert "Tell us about your rollout" in html           # heading override wins
    # empty intro override falls back to the default (which interpolates the firm name)
    assert "Acme is scoping your project" in html
    assert _brand_present(html)                            # brand never overridable


def test_override_cannot_inject_html():
    _subject, html = render_questionnaire_email("Acme", "https://app/q/x", fields={"heading": "<img src=x onerror=alert(1)>"})
    assert "<img src=x" not in html
    assert "&lt;img" in html


def test_submission_notice_includes_title_url_and_brand():
    html = client_submission_notice_email_html("Mobile App Rebuild", "https://app/projects")
    assert "Mobile App Rebuild" in html
    assert "https://app/projects" in html
    assert "Review the answers" in html
    assert _brand_present(html)


def test_account_and_support_emails_carry_the_aligniq_name():
    for html in (
        password_reset_email_html("Ada", "https://app/reset-password?token=t"),
        email_verification_email_html("Ada", "https://api/verify?token=t"),
        support_confirmation_html("Ada", "GIQ-ABC123", "Login help"),
        support_reply_html("Ada", "GIQ-ABC123", "We fixed it."),
    ):
        assert "Align" in html and ">IQ<" in html
        assert "Grounded" not in html
