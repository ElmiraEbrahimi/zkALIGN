from __future__ import annotations

import hashlib
import struct

DOMAIN = b"zkALIGN:trace:v1"


def canonical_trace_bytes(activity_ids: list[int], max_trace_length: int) -> bytes:
    if len(activity_ids) > max_trace_length:
        raise ValueError("trace exceeds configured maximum")
    if any(activity <= 0 for activity in activity_ids):
        raise ValueError("zero is reserved for padding")
    padded = [*activity_ids, *([0] * (max_trace_length - len(activity_ids)))]
    return DOMAIN + struct.pack(">I", len(activity_ids)) + b"".join(
        struct.pack(">I", activity) for activity in padded
    )


def commit_trace(activity_ids: list[int], salt: bytes, max_trace_length: int = 16) -> str:
    if len(salt) < 16:
        raise ValueError("use at least 128 bits of random salt")
    encoded = canonical_trace_bytes(activity_ids, max_trace_length)
    return hashlib.sha256(encoded + salt).hexdigest()
