#!/usr/bin/env python3
"""
compute_artifact_hash.py - AOW Spec v1.2 Candidate

Calculates the canonical artifact_content_hash of a paper.json submission.
Ensures identical SHA-256 calculation across all peer environments by:
1. Loading paper.json
2. Stripping variable signing/attestation fields:
   - attestation.peer_signatures
   - attestation.point_in_time.jwt
   - attestation.artifact_content_hash (self-reference)
3. Canonicalizing JSON keys (sorted, compact separators ',':':')
4. Emitting the SHA-256 hex digest
"""

import json
import sys
import copy
import hashlib
from pathlib import Path

def get_canonical_artifact_dict(paper_dict: dict) -> dict:
    """Returns a sanitized deepcopy of paper_dict ready for hashing."""
    data = copy.deepcopy(paper_dict)
    
    # Strip signature and self-referential fields in attestation block
    if "attestation" in data and isinstance(data["attestation"], dict):
        att = data["attestation"]
        att.pop("peer_signatures", None)
        att.pop("artifact_content_hash", None)
        if "point_in_time" in att and isinstance(att["point_in_time"], dict):
            att["point_in_time"].pop("jwt", None)
            
    # Also strip any top-level signature/hash if present
    data.pop("peer_signatures", None)
    data.pop("artifact_content_hash", None)
    
    return data

def compute_artifact_content_hash(paper_dict: dict) -> str:
    """Computes SHA-256 of the canonical JSON serialization."""
    canonical_dict = get_canonical_artifact_dict(paper_dict)
    canonical_bytes = json.dumps(
        canonical_dict,
        sort_keys=True,
        separators=(',', ':'),
        ensure_ascii=False
    ).encode('utf-8')
    return hashlib.sha256(canonical_bytes).hexdigest()

def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <path/to/paper.json>", file=sys.stderr)
        sys.exit(1)

    paper_path = Path(sys.argv[1])
    if not paper_path.is_file():
        print(f"Error: {paper_path} not found", file=sys.stderr)
        sys.exit(1)

    with open(paper_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    hash_val = compute_artifact_content_hash(data)
    print(hash_val)

if __name__ == "__main__":
    main()
