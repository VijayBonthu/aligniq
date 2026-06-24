"""Signup email hygiene: format check + disposable/throwaway-domain blocklist.

The blocklist (`src/data/disposable_email_domains.txt`) holds known temp-mail providers
only — free consumer providers (gmail/outlook/yahoo) are NOT disposable and stay allowed,
since legitimate customers use them. Deliverability is enforced separately by the
email-verification flow (the link must be clicked), so we don't do MX lookups here.

Loaded once at import (the set is small). Pure + import-light so it's unit-testable.
"""
from __future__ import annotations

import os
import re

from utils.logger import logger

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

_BLOCKLIST_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "disposable_email_domains.txt")


def _load_disposable_domains() -> set[str]:
    domains: set[str] = set()
    try:
        with open(_BLOCKLIST_PATH, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip().lower()
                if line and not line.startswith("#"):
                    domains.add(line)
    except FileNotFoundError:
        logger.error(f"Disposable-email blocklist not found at {_BLOCKLIST_PATH}; disposable check disabled")
    return domains


_DISPOSABLE_DOMAINS = _load_disposable_domains()


def normalize_email(email: str) -> str:
    """Trim + lowercase. Email is treated case-insensitively everywhere (login lookups,
    link-by-email), so storing normalized keeps everything consistent."""
    return (email or "").strip().lower()


def is_valid_email_format(email: str) -> bool:
    """Cheap structural sanity check (the Registration model field is a bare str)."""
    email = (email or "").strip()
    return bool(_EMAIL_RE.match(email)) and len(email) <= 254


def _domain_of(email: str) -> str:
    return normalize_email(email).rsplit("@", 1)[-1] if "@" in (email or "") else ""


def is_disposable_email(email: str) -> bool:
    """True if the email's domain is a known disposable/throwaway provider."""
    domain = _domain_of(email)
    return bool(domain) and domain in _DISPOSABLE_DOMAINS
