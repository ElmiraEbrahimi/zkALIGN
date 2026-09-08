from __future__ import annotations

import hashlib
from dataclasses import dataclass

Hash = bytes
LEAF_DOMAIN = b"zkALIGN:smt:leaf:v1"
EMPTY_DOMAIN = b"zkALIGN:smt:empty:v1"
NODE_DOMAIN = b"zkALIGN:smt:node:v1"


def sha256(*parts: bytes) -> Hash:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part)
    return digest.digest()


@dataclass(frozen=True)
class SparseMerkleProof:
    key: int
    siblings: tuple[str, ...]
    exists: bool

    def to_dict(self) -> dict[str, object]:
        return {"key": self.key, "siblings": list(self.siblings), "exists": self.exists}

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> "SparseMerkleProof":
        return cls(
            key=int(raw["key"]),
            siblings=tuple(str(item) for item in raw["siblings"]),
            exists=bool(raw["exists"]),
        )


class SparseMerkleTree:
    """Fixed-depth sparse Merkle tree with append-safe leaf insertion.

    Keys are public integer positions. Values are already-hashed trace
    commitments. Only non-empty nodes are stored; default hashes represent the
    untouched remainder of the key space.
    """

    def __init__(self, depth: int = 32) -> None:
        if not 1 <= depth <= 63:
            raise ValueError("depth must be between 1 and 63")
        self.depth = depth
        self.values: dict[int, Hash] = {}
        self.nodes: dict[tuple[int, int], Hash] = {}
        self.empty: list[Hash] = [sha256(EMPTY_DOMAIN)]
        for _ in range(depth):
            self.empty.append(sha256(NODE_DOMAIN, self.empty[-1], self.empty[-1]))

    def _check_key(self, key: int) -> None:
        if not 0 <= key < (1 << self.depth):
            raise ValueError(f"key {key} is outside the {self.depth}-bit tree")

    @staticmethod
    def leaf_hash(key: int, value: Hash) -> Hash:
        if len(value) != 32:
            raise ValueError("leaf value must be a 32-byte commitment")
        return sha256(LEAF_DOMAIN, key.to_bytes(8, "big"), value)

    def root(self) -> Hash:
        return self.nodes.get((self.depth, 0), self.empty[self.depth])

    def insert(self, key: int, value: Hash) -> Hash:
        self._check_key(key)
        if key in self.values:
            raise ValueError(f"sparse Merkle key {key} is already occupied")
        self.values[key] = value
        position = key
        current = self.leaf_hash(key, value)
        self.nodes[(0, position)] = current
        for level in range(self.depth):
            sibling_position = position ^ 1
            sibling = self.nodes.get((level, sibling_position), self.empty[level])
            if position & 1:
                current = sha256(NODE_DOMAIN, sibling, current)
            else:
                current = sha256(NODE_DOMAIN, current, sibling)
            position >>= 1
            self.nodes[(level + 1, position)] = current
        return current

    def proof(self, key: int) -> SparseMerkleProof:
        self._check_key(key)
        position = key
        siblings: list[str] = []
        for level in range(self.depth):
            siblings.append(
                self.nodes.get((level, position ^ 1), self.empty[level]).hex()
            )
            position >>= 1
        return SparseMerkleProof(key, tuple(siblings), key in self.values)

    def verify(self, value: Hash | None, proof: SparseMerkleProof, root: Hash) -> bool:
        self._check_key(proof.key)
        if len(proof.siblings) != self.depth or len(root) != 32:
            return False
        if proof.exists != (value is not None):
            return False
        current = (
            self.leaf_hash(proof.key, value)
            if value is not None
            else self.empty[0]
        )
        position = proof.key
        for sibling_hex in proof.siblings:
            try:
                sibling = bytes.fromhex(sibling_hex)
            except ValueError:
                return False
            if len(sibling) != 32:
                return False
            if position & 1:
                current = sha256(NODE_DOMAIN, sibling, current)
            else:
                current = sha256(NODE_DOMAIN, current, sibling)
            position >>= 1
        return current == root

    @classmethod
    def from_items(
        cls, items: list[tuple[int, Hash]], depth: int = 32
    ) -> "SparseMerkleTree":
        tree = cls(depth)
        for key, value in items:
            tree.insert(key, value)
        return tree
