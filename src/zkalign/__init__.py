"""zkALIGN reference implementation."""

from .alignment import find_min_cost_alignment
from .append_log import AppendOnlyTraceLog, trace_commitment
from .commitment import commit_trace
from .model import ProcessModel, load_model
from .verifier import PublicStatement, VerificationResult, verify_witness
from .sparse_merkle import SparseMerkleProof, SparseMerkleTree

__all__ = [
    "ProcessModel",
    "PublicStatement",
    "VerificationResult",
    "AppendOnlyTraceLog",
    "SparseMerkleProof",
    "SparseMerkleTree",
    "commit_trace",
    "find_min_cost_alignment",
    "load_model",
    "trace_commitment",
    "verify_witness",
]
