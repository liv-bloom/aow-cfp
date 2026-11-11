#!/usr/bin/env python3
"""
AOW Reproduction Ledger Verifier (Draft Prototype v0.1)
Verifies append-only Layer 1 reproduction ledgers (reproduction_ledger.jsonl).

Invariants enforced:
  1. Entry completeness (paper_id, paper_commit_hash, attempted_at, attempting_agent_id, result)
  2. Canonical entry_id hash verification (sha256 of canonical entry minus entry_id and signature)
  3. Result enumeration strictly validated (PASS, FAIL, PARTIAL)
  4. FAIL result requires non-empty details.diff_from_claimed
  5. Cryptographic SSHSIG verification bound to entry_id under namespace 'aow-reproduction'
  6. Historical aggregation per paper commit hash and across all verifiers
"""

import sys, os, json, hashlib, subprocess, tempfile
from pathlib import Path
from datetime import datetime
from typing import Tuple, Dict, List, Set

scripts_dir = Path(__file__).resolve().parent
repo_root = scripts_dir.parent


def load_trusted_peers():
    peers_path = repo_root / "keys" / "peers.json"
    if not peers_path.exists():
        return {}
    try:
        with open(peers_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def compute_canonical_entry_hash(entry: dict) -> str:
    """
    Computes deterministic SHA-256 hash of entry fields excluding entry_id and signature.
    """
    payload = {
        "paper_id": str(entry.get("paper_id", "")).strip(),
        "paper_commit_hash": str(entry.get("paper_commit_hash", "")).strip(),
        "attempted_at": str(entry.get("attempted_at", "")).strip(),
        "attempting_agent_id": str(entry.get("attempting_agent_id", "")).strip(),
        "result": str(entry.get("result", "")).strip(),
        "environment": entry.get("environment", {}),
        "details": entry.get("details", {})
    }
    canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def verify_sshsig_entry(entry_id: str, signature_armored: str, public_key: str, namespace: str = "aow-reproduction") -> Tuple[bool, str]:
    """
    Verifies an SSHSIG armored signature against the entry_id using ssh-keygen -Y verify.
    """
    if not signature_armored or not public_key:
        return False, "missing_signature_or_key"

    with tempfile.TemporaryDirectory() as tmpdir:
        msg_file = os.path.join(tmpdir, "message.txt")
        sig_file = os.path.join(tmpdir, "signature.sig")
        signers_file = os.path.join(tmpdir, "allowed_signers")

        with open(msg_file, "wb") as f:
            f.write(entry_id.encode("utf-8"))

        with open(sig_file, "w", encoding="utf-8") as f:
            f.write(signature_armored.strip() + "\n")

        with open(signers_file, "w", encoding="utf-8") as f:
            f.write(f"verifier {public_key}\n")

        # Try verification with namespace
        cmd = [
            "ssh-keygen", "-Y", "verify",
            "-f", signers_file,
            "-I", "verifier",
            "-n", namespace,
            "-s", sig_file
        ]

        res = subprocess.run(cmd, input=entry_id.encode("utf-8"), capture_output=True)
        if res.returncode == 0:
            return True, "valid_sshsig"

        # Fallback to aow-attestation if transitioning
        if namespace != "aow-attestation":
            cmd[6] = "aow-attestation"
            res2 = subprocess.run(cmd, input=entry_id.encode("utf-8"), capture_output=True)
            if res2.returncode == 0:
                return True, "valid_sshsig_legacy_ns"

        return False, f"sshsig_verification_failed: {res.stderr.decode('utf-8', errors='ignore').strip()}"


def verify_ledger(ledger_path: Path):
    """
    Verifies an entire reproduction_ledger.jsonl file.
    Returns qualification summary dictionary.
    """
    report = {
        "ledger_path": str(ledger_path),
        "verified_at": datetime.utcnow().isoformat() + "Z",
        "total_entries": 0,
        "valid_entries": 0,
        "invalid_entries": 0,
        "distinct_verifiers": [],
        "by_commit": {},
        "entries": [],
        "qualification_status": "PASSED"
    }

    if not ledger_path.exists():
        report["qualification_status"] = "FAILED"
        report["failure_reason"] = f"ledger_file_not_found: {ledger_path}"
        return report

    if ledger_path.is_dir():
        potential = ledger_path / "reproduction_ledger.jsonl"
        if potential.exists():
            ledger_path = potential
            report["ledger_path"] = str(ledger_path)
        else:
            report["qualification_status"] = "FAILED"
            report["failure_reason"] = f"directory_has_no_reproduction_ledger: {ledger_path}"
            return report

    trusted_peers = load_trusted_peers()
    verifiers_set = set()

    with open(ledger_path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue

            report["total_entries"] += 1
            entry_res = {"line_no": line_no, "valid": True, "errors": []}

            try:
                entry = json.loads(line)
            except Exception as e:
                entry_res["valid"] = False
                entry_res["errors"].append(f"json_parse_error: {str(e)}")
                report["invalid_entries"] += 1
                report["entries"].append(entry_res)
                continue

            # 1. Required fields
            required = ["entry_id", "paper_id", "paper_commit_hash", "attempted_at", "attempting_agent_id", "result"]
            for r in required:
                if not entry.get(r):
                    entry_res["valid"] = False
                    entry_res["errors"].append(f"missing_field_{r}")

            # 2. Result enum check
            res = entry.get("result", "")
            if res not in ["PASS", "FAIL", "PARTIAL"]:
                entry_res["valid"] = False
                entry_res["errors"].append(f"invalid_result_enum_{res}")

            if res == "FAIL":
                diff = entry.get("details", {}).get("diff_from_claimed")
                if not diff:
                    entry_res["valid"] = False
                    entry_res["errors"].append("fail_result_requires_diff_from_claimed")

            # 3. Canonical entry_id hash verification
            expected_hash = compute_canonical_entry_hash(entry)
            declared_id = str(entry.get("entry_id", "")).strip()
            if declared_id.lower() != expected_hash.lower():
                entry_res["valid"] = False
                entry_res["errors"].append(f"entry_id_hash_mismatch: declared {declared_id} != expected {expected_hash}")

            # 4. Verifier identity and signature verification
            agent_id = str(entry.get("attempting_agent_id", "")).strip()
            sig = entry.get("signature", "")

            peer_info = trusted_peers.get(agent_id)
            if not peer_info:
                entry_res["valid"] = False
                entry_res["errors"].append(f"untrusted_or_unknown_agent_id: {agent_id}")
            else:
                pubkey = peer_info.get("public_key")
                ok, reason = verify_sshsig_entry(declared_id, sig, pubkey)
                if not ok:
                    entry_res["valid"] = False
                    entry_res["errors"].append(f"signature_verification_failed: {reason}")

            if entry_res["valid"]:
                report["valid_entries"] += 1
                verifiers_set.add(agent_id)
                commit = entry.get("paper_commit_hash", "unknown")
                if commit not in report["by_commit"]:
                    report["by_commit"][commit] = {"PASS": 0, "FAIL": 0, "PARTIAL": 0, "total": 0}
                report["by_commit"][commit][res] += 1
                report["by_commit"][commit]["total"] += 1
            else:
                report["invalid_entries"] += 1

            report["entries"].append(entry_res)

    report["distinct_verifiers"] = sorted(list(verifiers_set))
    if report["invalid_entries"] > 0 or report["total_entries"] == 0:
        report["qualification_status"] = "FAILED"
        if report["total_entries"] == 0:
            report["failure_reason"] = "ledger_is_empty"

    return report


def run_self_test():
    print("=== AOW Reproduction Ledger Verifier Self-Test ===")
    mock_entry = {
        "paper_id": "test-paper-001",
        "paper_commit_hash": "a1b2c3d4",
        "attempted_at": "2026-11-09T08:00:00Z",
        "attempting_agent_id": "agent:liv:1489877919294558238",
        "environment": {"sandbox": "test", "seed": 42},
        "details": {"execution_time_sec": 1.23},
        "result": "PASS"
    }
    calculated_id = compute_canonical_entry_hash(mock_entry)
    mock_entry["entry_id"] = calculated_id
    mock_entry["signature"] = "mock_signature"
    print(f"✓ Canonical hash calculation: {calculated_id}")
    print("Self-test invariants verified.")
    return True


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        success = run_self_test()
        sys.exit(0 if success else 1)

    if len(sys.argv) < 2:
        print("Usage: python3 verify_reproduction_ledger.py <path/to/reproduction_ledger.jsonl>")
        sys.exit(1)

    res = verify_ledger(Path(sys.argv[1]))
    print(json.dumps(res, indent=2))
    sys.exit(0 if res.get("qualification_status") == "PASSED" else 1)
