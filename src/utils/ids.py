"""
Time-ordered identifier generation (UUIDv7).

Every primary key in the app is a UUID string. We use **UUIDv7** (RFC 9562)
rather than UUIDv4 so that ids are *time-sortable*: the first 48 bits are a
Unix-millisecond timestamp, so newly minted ids cluster together in B-tree
indexes (better insert locality, cheaper range-by-time scans) and carry a
natural shard key if we ever partition the DB by time.

Pure-Python, zero native dependencies (stdlib `uuid` only grows a v7 factory
in Python 3.14). Output is a canonical hyphenated UUID string, so it is a
drop-in replacement for `str(uuid.uuid4())` — existing v4 ids in the DB remain
valid and comparable; only newly created rows become time-ordered.
"""
from __future__ import annotations

import os
import time
from uuid import UUID


def uuid7() -> UUID:
    """Return a UUIDv7 (RFC 9562) built from the current wall-clock time."""
    # 48-bit Unix timestamp in milliseconds.
    unix_ms = time.time_ns() // 1_000_000

    # 74 random bits: 12 for rand_a, 62 for rand_b.
    rnd = os.urandom(10)
    rand_a = int.from_bytes(rnd[0:2], "big") & 0x0FFF          # 12 bits
    rand_b = int.from_bytes(rnd[2:10], "big") & ((1 << 62) - 1)  # 62 bits

    value = (
        (unix_ms & 0xFFFFFFFFFFFF) << 80   # ts: bits 80..127
        | (0x7 << 76)                       # version 7: bits 76..79
        | (rand_a << 64)                    # rand_a: bits 64..75
        | (0b10 << 62)                      # variant: bits 62..63
        | rand_b                            # rand_b: bits 0..61
    )
    return UUID(int=value)


def new_id() -> str:
    """Canonical UUIDv7 string — drop-in replacement for str(uuid.uuid4())."""
    return str(uuid7())


def new_hex(prefix: str = "") -> str:
    """UUIDv7 as a 32-char hex string, optionally prefixed (e.g. 'firm_')."""
    return prefix + uuid7().hex
