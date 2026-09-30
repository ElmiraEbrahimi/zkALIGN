"""BN254 MiMC, matching gnark-crypto's 110-round x^5 construction.

Application data is hashed only with MiMC. Byte hashing has explicit part
lengths and 31-byte chunks, so arbitrary bytes are never reduced modulo p.
This Python implementation is a reference/data-preparation implementation,
not a constant-time implementation for hostile shared execution environments.
"""
from __future__ import annotations

from .mimc_constants import ROUND_CONSTANTS

FIELD_MODULUS = 21888242871839275222246405745257275088548364400416034343698204186575808495617
BYTE_DOMAIN = 20261001  # Disjoint from trace, leaf and all 32 node domains.
TRACE_DOMAIN = 20260910
LEAF_DOMAIN = 20260911
NODE_DOMAIN = 20260912
TRACE_CAPACITY = 185
ACTIVITY_COUNT = 16
HASH_SCHEME = "bn254-mimc-gnark-v2"


def hash_fields(*values: int) -> bytes:
    state = 0
    for value in values:
        if not 0 <= value < FIELD_MODULUS:
            raise ValueError("noncanonical BN254 field element")
        encrypted = value
        for constant in ROUND_CONSTANTS:
            encrypted = pow((encrypted + state + constant) % FIELD_MODULUS, 5, FIELD_MODULUS)
        state = (encrypted + 2 * state + value) % FIELD_MODULUS
    return state.to_bytes(32, "big")


def mimc_bytes(*parts: bytes) -> bytes:
    fields = [BYTE_DOMAIN, len(parts)]
    for part in parts:
        fields.append(len(part))
        fields.extend(int.from_bytes(part[i:i + 31], "big") for i in range(0, len(part), 31))
    return hash_fields(*fields)


def file_mimc(path) -> str:
    return mimc_bytes(b"zkALIGN:file:v2", path.read_bytes()).hex()


def trace_hash(activity_ids: list[int], salt: bytes) -> bytes:
    if len(activity_ids) > TRACE_CAPACITY or any(not 1 <= a <= ACTIVITY_COUNT for a in activity_ids):
        raise ValueError("trace exceeds the circuit capacity or activity dictionary")
    if len(salt) != 32:
        raise ValueError("trace salts must be 32 bytes")
    # The current Go witness adapter reduces the 256-bit salt into the field.
    # Match it exactly. Byte-file hashing above never uses such reduction.
    return hash_fields(TRACE_DOMAIN, len(activity_ids), *activity_ids,
                       *([0] * (TRACE_CAPACITY - len(activity_ids))),
                       int.from_bytes(salt, "big") % FIELD_MODULUS)


def field_from_hash(value: bytes) -> int:
    number = int.from_bytes(value, "big")
    if len(value) != 32 or number >= FIELD_MODULUS:
        raise ValueError("expected a canonical 32-byte MiMC field digest")
    return number
