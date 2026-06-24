"""Dynamic operational state — maintenance / read-only / feature flags.

Source of truth is the `site_settings` table (durable; Redis here is non-persistent
so it must NOT hold maintenance state). Reads go through a short in-process TTL cache
so the maintenance middleware stays off the hot DB path — only ~1 query per TTL window.
Admin writes call `invalidate()` so a toggle takes effect within a request or two
(no server restart). At `--workers 1` this is effectively instant; for multi-worker,
add a Redis pub/sub "invalidate" channel later (the TTL guarantees correctness regardless).

Fail-safe: if the DB read errors, we return the last good cache (or built-in defaults
with maintenance OFF) — a transient DB blip must never accidentally lock users out.
"""
from __future__ import annotations

import time
import copy
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from models import SiteSetting, sessionlocal
from utils.logger import logger

_TTL_SECONDS = 10.0

# Built-in defaults. Anything not set in the DB falls back here; per-key DB values
# are shallow-merged over these so a partial row can't drop a field.
DEFAULTS: Dict[str, Dict[str, Any]] = {
    "maintenance": {
        "on": False, "title": "", "message": "", "eta": "", "media_url": "",
        "allowlist_ips": [], "allowlist_emails": [],
        # Scope for an ACTIVE maintenance (`on`=True): when non-empty, ONLY these emails are
        # shown the maintenance page / blocked and everyone else uses the site normally;
        # empty = site-wide. (`on` is the master switch — empty list + off = nothing.)
        "target_emails": [],
    },
    "read_only": {"on": False, "message": ""},
    "feature_flags": {
        "signups_enabled": True, "logins_enabled": True, "pipeline_enabled": True,
    },
}

_cache: Optional[Dict[str, Any]] = None
_cache_at: float = 0.0


def _defaults() -> Dict[str, Any]:
    return copy.deepcopy(DEFAULTS)


def _load(db: Session) -> Dict[str, Any]:
    rows = {r.key: (r.value or {}) for r in db.query(SiteSetting).all()}
    out = _defaults()
    for key, default in DEFAULTS.items():
        out[key] = {**default, **(rows.get(key) or {})}
    return out


def get_ops_state(db: Optional[Session] = None) -> Dict[str, Any]:
    """Return the cached ops snapshot {maintenance, read_only, feature_flags}.
    Pass an existing session, or omit it and we open/close our own (used by the
    middleware, which has no request session)."""
    global _cache, _cache_at
    now = time.monotonic()
    if _cache is not None and (now - _cache_at) < _TTL_SECONDS:
        return _cache

    own = db is None
    if own:
        db = sessionlocal()
    try:
        state = _load(db)
    except Exception as e:
        logger.error(f"ops_state load failed, serving last-known/defaults: {e}")
        return _cache if _cache is not None else _defaults()
    finally:
        if own:
            db.close()

    _cache = state
    _cache_at = time.monotonic()
    return state


def invalidate() -> None:
    """Drop the cache so the next read reflects a just-written change immediately."""
    global _cache, _cache_at
    _cache = None
    _cache_at = 0.0


def upsert_setting(db: Session, key: str, value: Dict[str, Any], updated_by: Optional[str] = None) -> Dict[str, Any]:
    """Create or update a settings row, commit, and bust the cache. Returns the
    merged effective value (defaults <- stored)."""
    row = db.query(SiteSetting).filter(SiteSetting.key == key).first()
    if row is None:
        row = SiteSetting(key=key, value=value, updated_by=updated_by)
        db.add(row)
    else:
        # merge so a partial PATCH doesn't wipe sibling fields
        row.value = {**(row.value or {}), **value}
        row.updated_by = updated_by
    db.commit()
    invalidate()
    merged = {**DEFAULTS.get(key, {}), **(row.value or {})}
    return merged
