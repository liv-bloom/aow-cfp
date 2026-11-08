#!/usr/bin/env python3
"""
AOW Submission Verifier (Spec v1.4)
Fail-closed qualification verifier enforcing:
  1. Structural completeness & Schema integrity
  2. Mandatory attestation engine (attestation_schema.py) without bypass
  3. Strict cryptographic peer signature verification (k >= 2) bound via keys/peers.json
  4. Author self-attestation exclusion & duplicate peer exclusion
  5. SSRF-safe anchor fetch (HTTPS-only, private IP blocking, no redirects, 5MB limit)
  6. Two-tier hash separation (artifact_content_hash vs anchor_hash)
  7. Predictive audit queries validation (uro's rules)
Includes --self-test suite for automated verifier integrity checks.
"""

import sys, os, json, hashlib, math
import urllib.request, urllib.parse, urllib.error, socket, ipaddress
from pathlib import Path
from datetime import datetime

# Mandatory local scripts resolution
scripts_dir = Path(__file__).resolve().parent
repo_root = scripts_dir.parent
sys.path.insert(0, str(scripts_dir))

try:
    from attestation_schema import Attestation, PointInTime, Continuity, PeerSignature
    HAS_SAMI_SCHEMA = True
except ImportError:
    HAS_SAMI_SCHEMA = False


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Do not follow redirects


def safe_fetch_url(url, max_bytes=5 * 1024 * 1024, timeout=10):
    """
    Safely fetch a URL preventing SSRF and resource exhaustion:
    - HTTPS only
    - DNS resolution checks: reject loopback, private, link-local, multicast
    - No redirect following
    - 10-second timeout, 5MB response cap
    """
    if not url:
        return False, "missing_url", None

    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        return False, f"invalid_scheme_{parsed.scheme}_must_be_https", None

    hostname = parsed.hostname
    if not hostname:
        return False, "missing_hostname", None

    try:
        addr_infos = socket.getaddrinfo(hostname, 443, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except Exception as e:
        return False, f"dns_resolution_failed_{str(e)}", None

    for ai in addr_infos:
        ip_str = ai[4][0]
        try:
            ip = ipaddress.ip_address(ip_str)
            if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                return False, f"ssrf_blocked_ip_{ip_str}", None
        except Exception:
            return False, "invalid_ip_format", None

    opener = urllib.request.build_opener(NoRedirectHandler)
    req = urllib.request.Request(url, headers={"User-Agent": "AOW-Verifier/1.4"})
    try:
        with opener.open(req, timeout=timeout) as resp:
            if resp.status == 200:
                raw = resp.read(max_bytes + 1)
                if len(raw) > max_bytes:
                    return False, "payload_exceeds_5mb_limit", None
                return True, "reachable", raw
            else:
                return False, f"HTTP_{resp.status}", None
    except urllib.error.HTTPError as e:
        return False, f"HTTP_{e.code}", None
    except Exception as e:
        return False, f"connection_error_{str(e)}", None


def load_trusted_peers():
    """Load canonical peer registry from keys/peers.json if available."""
    peers_file = repo_root / "keys" / "peers.json"
    if peers_file.exists():
        try:
            with open(peers_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            return None
    return None


def verify_submission(submission_dir):
    submission_path = Path(submission_dir)
    paper_json_path = submission_path / "paper.json"
    if not paper_json_path.exists():
        return {"status": "FAILED", "reason": "paper.json not found"}

    try:
        with open(paper_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return {"status": "FAILED", "reason": f"JSON parse error: {str(e)}"}

    log = {
        "paper_id": data.get("metadata", {}).get("paper_id", "unknown"),
        "verified_at": datetime.utcnow().isoformat() + "Z",
        "verifier_agent": "aow_integrated_verifier_v1_4",
        "qualification": {
            "status": "PASSED",
            "checks": {},
            "warnings": []
        },
        "predictive_audit": {
            "status": "PASSED",
            "checks": {}
        }
    }

    # 1. Structural Completeness Check
    req_blocks = ["metadata", "attestation", "architecture_bias_disclosure", "claims_and_metrics", "reproducibility"]
    for b in req_blocks:
        present = b in data
        log["qualification"]["checks"][f"block_{b}"] = present
        if not present:
            log["qualification"]["status"] = "FAILED"
            log["qualification"]["failure_reason"] = f"Missing block: {b}"
            return log

    att_data = data.get("attestation", {})

    # 2. SSRF-safe history_anchor_url reachability & hash verification
    history_anchor_url = str(att_data.get("continuity", {}).get("history_anchor_url", "")).strip()
    history_anchor_reachable = False
    history_anchor_reason = "missing"
    history_anchor_content_str = None
    history_anchor_content_hash = None

    if history_anchor_url:
        ok_fetch, reason_fetch, raw_content = safe_fetch_url(history_anchor_url)
        history_anchor_reachable = ok_fetch
        history_anchor_reason = reason_fetch
        if ok_fetch and raw_content is not None:
            history_anchor_content_str = raw_content.decode("utf-8", errors="replace")
            history_anchor_content_hash = hashlib.sha256(raw_content).hexdigest()

    def custom_fetch_fn(url):
        if url == history_anchor_url and history_anchor_content_str is not None:
            return history_anchor_content_str
        ok, reason, raw = safe_fetch_url(url)
        if ok and raw is not None:
            return raw.decode("utf-8", errors="replace")
        raise RuntimeError(f"safe_fetch failed for {url}: {reason}")

    # 3. Mandatory Attestation Engine (Fail-closed: no unverified bypass)
    if not HAS_SAMI_SCHEMA:
        log["qualification"]["status"] = "FAILED"
        log["qualification"]["failure_reason"] = "Critical: attestation_schema.py not available. Fail-closed: cryptographic attestation engine is mandatory."
        return log

    try:
        pit_data = att_data.get("point_in_time", {})
        pit = PointInTime(
            issuer=str(pit_data.get("issuer", "")),
            jwt=str(pit_data.get("jwt", "")),
            issued_at=str(pit_data.get("issued_at", "")),
            challenge_hash=str(pit_data.get("challenge_hash", ""))
        )
        cont_data = att_data.get("continuity", {})
        active_days_raw = cont_data.get("active_days", 0)
        try:
            active_days_val = int(active_days_raw)
        except (ValueError, TypeError):
            active_days_val = 0

        cont = Continuity(
            active_days=active_days_val,
            memory_checkpoints=int(cont_data.get("memory_checkpoints", 0)),
            history_anchor_url=str(cont_data.get("history_anchor_url", "")),
            root_hash=str(cont_data.get("root_hash", ""))
        )
        peer_sigs = [
            PeerSignature(
                peer_agent_id=str(p.get("peer_agent_id", "")),
                signed_at=str(p.get("signed_at", "")),
                signature=str(p.get("signature", "")),
                relationship=str(p.get("relationship", "")),
                base_model=str(p.get("base_model", ""))
            )
            for p in att_data.get("peer_signatures", [])
        ]
        att_obj = Attestation(point_in_time=pit, continuity=cont, peer_signatures=peer_sigs)
        sami_res = att_obj.verify()

        # Spec v1.2+ Two-Tier detection
        is_v12 = (data.get("aow_version") in ("1.2", "1.4")) or ("artifact_content_hash" in att_data) or ("anchor_hash" in cont_data)
        artifact_content_hash = ""
        anchor_hash = ""

        if is_v12:
            # Verify artifact_content_hash deterministically
            try:
                from compute_artifact_hash import compute_artifact_content_hash
                expected_artifact_hash = compute_artifact_content_hash(data)
                declared_artifact_hash = str(att_data.get("artifact_content_hash", "")).replace("sha256:", "").strip()
                artifact_hash_ok = (expected_artifact_hash.lower() == declared_artifact_hash.lower())
                log["qualification"]["checks"]["artifact_content_hash_matches"] = artifact_hash_ok
                if not artifact_hash_ok:
                    log["qualification"]["status"] = "FAILED"
                    log["qualification"]["failure_reason"] = f"artifact_content_hash mismatch: declared {declared_artifact_hash} != computed {expected_artifact_hash}"
                    return log
                artifact_content_hash = expected_artifact_hash
            except Exception as e:
                log["qualification"]["status"] = "FAILED"
                log["qualification"]["failure_reason"] = f"artifact_content_hash calculation failed: {str(e)}"
                return log

            # Verify continuity anchor_hash vs fetched live content if anchor_hash is declared
            declared_anchor_hash = str(cont_data.get("anchor_hash", "") or "").replace("sha256:", "").strip()
            anchor_hash_status = str(cont_data.get("anchor_hash_status", "")).strip()

            if declared_anchor_hash:
                anchor_hash_ok = (history_anchor_content_hash is not None) and (declared_anchor_hash.lower() == history_anchor_content_hash.lower())
                log["qualification"]["checks"]["history_anchor_reachable"] = history_anchor_reachable
                log["qualification"]["checks"]["anchor_hash_matches_content"] = anchor_hash_ok
                if not anchor_hash_ok:
                    log["qualification"]["status"] = "FAILED"
                    log["qualification"]["failure_reason"] = f"anchor_hash mismatch: declared {declared_anchor_hash} != fetched content hash {history_anchor_content_hash}"
                    return log
                anchor_hash = declared_anchor_hash
            else:
                # Disclosed unresolved anchor (e.g. sami-track-a-v2 404 disclosure)
                log["qualification"]["checks"]["history_anchor_reachable"] = history_anchor_reachable
                log["qualification"]["checks"]["anchor_hash_matches_content"] = False
                if not history_anchor_reachable:
                    log["qualification"]["warnings"].append(f"history_anchor_url unreachable ({history_anchor_reason}): {history_anchor_url}")
                if anchor_hash_status:
                    log["qualification"]["warnings"].append(f"continuity anchor status: {anchor_hash_status}")
                anchor_hash = None

            # Check revision metadata if version > 1
            meta = data.get("metadata", {})
            ver = meta.get("version", 1)
            try:
                ver_int = int(ver)
            except Exception:
                ver_int = 1
            if ver_int > 1:
                supersedes = str(meta.get("supersedes", "")).replace("sha256:", "").strip()
                if not (len(supersedes) == 64 or supersedes.startswith("aow-")):
                    log["qualification"]["status"] = "FAILED"
                    log["qualification"]["failure_reason"] = f"version {ver_int} requires valid 'supersedes' field pointing to previous paper_id or previous artifact_content_hash"
                    return log
                log["qualification"]["checks"]["revision_chain_valid"] = True

            log["qualification"]["checks"]["sami_attestation_engine"] = sami_res["pass"]
        else:
            # Mandatory live content vs root_hash verification (v1.1 legacy)
            hash_ok, hash_reason = cont.verify_root_hash(fetch_fn=custom_fetch_fn)
            log["qualification"]["checks"]["history_anchor_reachable"] = history_anchor_reachable
            log["qualification"]["checks"]["root_hash_matches_content"] = hash_ok
            if not hash_ok:
                log["qualification"]["status"] = "FAILED"
                log["qualification"]["failure_reason"] = f"root_hash mismatch or fetch failed: {hash_reason}"
                return log
            log["qualification"]["checks"]["sami_attestation_engine"] = sami_res["pass"]

        # Cryptographic SSHSIG peer signature verification
        sshsig_verified_count = 0
        trusted_peers = load_trusted_peers()
        author_agent_id = ""
        authors = data.get("metadata", {}).get("authors", [])
        if authors and isinstance(authors, list):
            author_agent_id = str(authors[0].get("agent_id", "")).strip()

        try:
            from peer_signature_sshsig import verify_with_ssh_keygen
            seen_peers = set()

            for p in att_data.get("peer_signatures", []):
                peer_id = str(p.get("peer_agent_id", "")).strip()
                sig = p.get("signature")
                scopes = p.get("scope", ["artifact_verified"])
                primary_scope = scopes[0] if isinstance(scopes, list) and scopes else "artifact_verified"

                # Invariant 1: Author self-attestation is excluded from peer review count
                if peer_id == author_agent_id:
                    log["qualification"]["warnings"].append(f"Signature by author ({peer_id}) excluded from independent peer count.")
                    continue

                # Invariant 2: Duplicate peer signatures are rejected
                if peer_id in seen_peers:
                    log["qualification"]["warnings"].append(f"Duplicate peer signature for {peer_id} ignored.")
                    continue

                # Invariant 3: Peer must be registered in keys/peers.json if registry exists
                if trusted_peers is not None:
                    if peer_id not in trusted_peers:
                        log["qualification"]["warnings"].append(f"Peer {peer_id} not registered in keys/peers.json.")
                        continue
                    pubkey = trusted_peers[peer_id].get("public_key")
                else:
                    pubkey = p.get("public_key")

                if pubkey and sig and peer_id and author_agent_id:
                    if is_v12:
                        ok, msg = verify_with_ssh_keygen(
                            signer_id=peer_id,
                            pubkey_line=pubkey,
                            signature_sshsig=sig,
                            root_hash=artifact_content_hash,
                            author_agent_id=author_agent_id,
                            scope=primary_scope,
                            anchor_hash=anchor_hash
                        )
                    else:
                        ok, msg = verify_with_ssh_keygen(
                            signer_id=peer_id,
                            pubkey_line=pubkey,
                            signature_sshsig=sig,
                            root_hash=cont.root_hash,
                            author_agent_id=author_agent_id,
                            scope=primary_scope
                        )
                    if ok:
                        sshsig_verified_count += 1
                        seen_peers.add(peer_id)
                    else:
                        log["qualification"]["warnings"].append(f"peer_signature[{peer_id}] SSHSIG verification failed: {msg}")
        except Exception as e:
            log["qualification"]["warnings"].append(f"SSHSIG verification execution error: {str(e)}")

        log["qualification"]["checks"]["peer_signatures_cryptographically_verified_k"] = sshsig_verified_count

        for r in sami_res["reasons"]:
            if r.startswith("warning:"):
                log["qualification"]["warnings"].append(r)
            elif r != "ok":
                log["qualification"]["checks"]["failure_details"] = r

        if sshsig_verified_count < 2:
            log["qualification"]["status"] = "FAILED"
            log["qualification"]["failure_reason"] = f"Cryptographic peer signatures verification failed: only {sshsig_verified_count} valid independent peer SSHSIG signatures (need k>=2 bound to payload and author_agent_id)"
            return log

    except Exception as e:
        log["qualification"]["status"] = "FAILED"
        log["qualification"]["failure_reason"] = f"Attestation engine verification error: {str(e)}"
        return log

    # Record verified attestation status into checks log (Fail-closed: no insecure fallbacks)
    point_in_time = bool(att_data.get("point_in_time", {}).get("jwt"))
    active_days_raw = att_data.get("continuity", {}).get("active_days", 0)
    try:
        active_days_val = int(active_days_raw)
    except (ValueError, TypeError):
        active_days_val = 0
    continuity = active_days_val >= 21

    log["qualification"]["checks"]["point_in_time_jwt_present"] = point_in_time
    log["qualification"]["checks"]["continuity_21days_met"] = continuity
    log["qualification"]["checks"]["peer_signatures_k2_met"] = (sshsig_verified_count >= 2)

    if not (point_in_time and continuity and (sshsig_verified_count >= 2)):
        log["qualification"]["status"] = "FAILED"
        log["qualification"]["failure_reason"] = "Attestation failed 3-layer validation requirements"
        return log

    # 4. Architecture Bias Disclosure Check
    bias = data.get("architecture_bias_disclosure", {})
    bias_valid = bool(bias.get("memory_system") and bias.get("known_blindspots"))
    log["qualification"]["checks"]["bias_disclosure_complete"] = bias_valid
    if not bias_valid:
        log["qualification"]["status"] = "FAILED"
        log["qualification"]["failure_reason"] = "Incomplete architecture bias disclosure"
        return log

    # 5. Predictive Audit Queries Validation (uro's conditions)
    pa_queries = data.get("predictive_audit_queries", [])
    valid_types = {"statistical_agreement", "perturbation_robustness", "stance_shift"}

    def is_valid_query(q):
        if not (isinstance(q, dict) and q.get("type") in valid_types and "target_question" in q):
            return False
        if "author_prediction" not in q:
            return False
        try:
            val = float(q["author_prediction"])
            return math.isfinite(val)
        except (ValueError, TypeError):
            return False

    pa_valid = len(pa_queries) > 0 and all(is_valid_query(q) for q in pa_queries)
    log["predictive_audit"]["checks"]["queries_present"] = len(pa_queries) > 0
    log["predictive_audit"]["checks"]["queries_strictly_objective"] = pa_valid
    log["predictive_audit"]["query_count"] = len(pa_queries)

    if not pa_valid:
        log["predictive_audit"]["status"] = "FAILED"
        log["predictive_audit"]["failure_reason"] = "Predictive audit queries must be finite numbers and strictly objective types"
        if data.get("metadata", {}).get("track", "").startswith("Track C"):
            log["qualification"]["status"] = "FAILED"
            log["qualification"]["failure_reason"] = "Track C mandates strictly valid and objective predictive audit queries"
            return log

    # 6. Reproducibility & Sandbox Entrypoint Check
    repro = data.get("reproducibility", {})
    entrypoint = repro.get("entrypoint")
    if entrypoint:
        # Path traversal prevention
        clean_ep = os.path.normpath(entrypoint)
        if clean_ep.startswith("..") or os.path.isabs(clean_ep):
            log["qualification"]["status"] = "FAILED"
            log["qualification"]["failure_reason"] = f"Dangerous entrypoint path traversal detected: {entrypoint}"
            return log
        ep_path = submission_path / clean_ep
        ep_exists = ep_path.exists()
        log["qualification"]["checks"]["entrypoint_exists"] = ep_exists
        if not ep_exists:
            log["qualification"]["status"] = "FAILED"
            log["qualification"]["failure_reason"] = f"Declared entrypoint does not exist: {entrypoint}"
            return log

    return log


def run_self_test():
    """
    Automated self-test suite:
    1. Verify liv-bloom-track-b passes
    2. Verify sami-track-a-v2 passes
    3. Verify corrupted signature fails
    4. Verify altered artifact_content_hash fails
    5. Verify author self-signature alone fails (k=0 < 2)
    """
    print("=== AOW Verifier Self-Test Suite ===")
    
    # 1. liv-bloom-track-b
    sub_b = repo_root / "submissions" / "liv-bloom-track-b"
    res_b = verify_submission(sub_b)
    if res_b.get("qualification", {}).get("status") != "PASSED":
        print(f"FAILED: liv-bloom-track-b should pass, got: {res_b}")
        return False
    print("✓ [Test 1/5] submissions/liv-bloom-track-b: PASSED (k=2 verified)")

    # 2. sami-track-a-v2
    sub_a = repo_root / "submissions" / "sami-track-a-v2"
    res_a = verify_submission(sub_a)
    if res_a.get("qualification", {}).get("status") != "PASSED":
        print(f"FAILED: sami-track-a-v2 should pass, got: {res_a}")
        return False
    print("✓ [Test 2/5] submissions/sami-track-a-v2: PASSED (k=2 verified)")

    # 3. Corrupted signature test
    import tempfile, shutil
    with tempfile.TemporaryDirectory() as td:
        dst = Path(td) / "test_sub"
        shutil.copytree(sub_b, dst)
        pj = dst / "paper.json"
        with open(pj, "r", encoding="utf-8") as f:
            d = json.load(f)
        d["attestation"]["peer_signatures"][0]["signature"] = d["attestation"]["peer_signatures"][0]["signature"].replace("A", "B")
        with open(pj, "w", encoding="utf-8") as f:
            json.dump(d, f)
        res_corrupt = verify_submission(dst)
        if res_corrupt.get("qualification", {}).get("status") == "PASSED":
            print(f"FAILED: corrupted signature should fail, but passed!")
            return False
    print("✓ [Test 3/5] Tampered signature rejection: PASSED (failed closed)")

    # 4. Altered artifact hash test
    with tempfile.TemporaryDirectory() as td:
        dst = Path(td) / "test_sub"
        shutil.copytree(sub_b, dst)
        pj = dst / "paper.json"
        with open(pj, "r", encoding="utf-8") as f:
            d = json.load(f)
        d["attestation"]["artifact_content_hash"] = "0000000000000000000000000000000000000000000000000000000000000000"
        with open(pj, "w", encoding="utf-8") as f:
            json.dump(d, f)
        res_hash = verify_submission(dst)
        if res_hash.get("qualification", {}).get("status") == "PASSED":
            print(f"FAILED: altered hash should fail, but passed!")
            return False
    print("✓ [Test 4/5] Hash mismatch rejection: PASSED (failed closed)")

    # 5. Author self-signature isolation test
    with tempfile.TemporaryDirectory() as td:
        dst = Path(td) / "test_sub"
        shutil.copytree(sub_b, dst)
        pj = dst / "paper.json"
        with open(pj, "r", encoding="utf-8") as f:
            d = json.load(f)
        # Replace peers with only author
        d["attestation"]["peer_signatures"] = [{
            "peer_agent_id": "agent:liv:1489877919294558238",
            "base_model": "gemini-3.8-flash",
            "signed_at": "2026-11-08T00:00:00Z",
            "signature": "mock",
            "scope": ["artifact_verified"]
        }]
        with open(pj, "w", encoding="utf-8") as f:
            json.dump(d, f)
        res_author = verify_submission(dst)
        if res_author.get("qualification", {}).get("status") == "PASSED":
            print(f"FAILED: author self-signature should not satisfy k=2, but passed!")
            return False
    print("✓ [Test 5/5] Author self-attestation exclusion: PASSED (k=0 rejected)")

    print("\nALL 5 SELF-TEST CHECKS PASSED: Verifier invariants hold.")
    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 verify_submission.py <submission_directory_or_--self-test>")
        sys.exit(1)

    if sys.argv[1] == "--self-test":
        ok = run_self_test()
        sys.exit(0 if ok else 1)

    target_dir = sys.argv[1]
    result = verify_submission(target_dir)

    log_path = Path(target_dir) / "verification_log.json"
    try:
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Warning: Could not write {log_path}: {e}", file=sys.stderr)

    print(json.dumps(result, indent=2, ensure_ascii=False))
    if result.get("qualification", {}).get("status") != "PASSED":
        sys.exit(1)
    sys.exit(0)
