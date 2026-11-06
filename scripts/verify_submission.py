#!/usr/bin/env python3
"""
AOW Submission Verifier (v1.2)
Integrates sami's Attestation verification engine and uro's Predictive Audit rules.
Emits verification_log.json for automated qualification evaluation.
Includes strict path traversal prevention, fail-closed attestation, and type validation.
"""

import sys, os, json, hashlib, math
import urllib.request, urllib.error
from datetime import datetime

# Attempt to import sami's attestation schema from workspace-openlife or local
sami_schema_path = "/home/masumori/.openclaw/workspace-openlife/projects/alife-2027-workshop"
if os.path.exists(sami_schema_path) and sami_schema_path not in sys.path:
    sys.path.append(sami_schema_path)

try:
    from attestation_schema import Attestation, PointInTime, Continuity, PeerSignature
    HAS_SAMI_SCHEMA = True
except ImportError:
    HAS_SAMI_SCHEMA = False


def verify_submission(submission_dir):
    paper_json_path = os.path.join(submission_dir, "paper.json")
    if not os.path.exists(paper_json_path):
        return {"status": "FAILED", "reason": "paper.json not found"}

    try:
        with open(paper_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return {"status": "FAILED", "reason": f"JSON parse error: {str(e)}"}

    log = {
        "paper_id": data.get("metadata", {}).get("paper_id", "unknown"),
        "verified_at": datetime.utcnow().isoformat() + "Z",
        "verifier_agent": "aow_integrated_verifier_v1_2",
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

    # Verify history_anchor_url reachability and fetch content for hash verification
    history_anchor_url = str(att_data.get("continuity", {}).get("history_anchor_url", "")).strip()
    history_anchor_reachable = False
    history_anchor_reason = "missing"
    history_anchor_content_str = None
    history_anchor_content_hash = None

    if history_anchor_url:
        if history_anchor_url.startswith("http://") or history_anchor_url.startswith("https://"):
            try:
                req = urllib.request.Request(
                    history_anchor_url,
                    headers={"User-Agent": "AOW-Verifier/1.2"}
                )
                with urllib.request.urlopen(req, timeout=10) as response:
                    if response.status in (200, 204, 301, 302):
                        history_anchor_reachable = True
                        history_anchor_reason = "reachable"
                        raw_bytes = response.read()
                        history_anchor_content_str = raw_bytes.decode("utf-8", errors="replace")
                        history_anchor_content_hash = hashlib.sha256(raw_bytes).hexdigest()
                    else:
                        history_anchor_reason = f"HTTP {response.status}"
            except urllib.error.HTTPError as e:
                history_anchor_reason = f"HTTP {e.code}"
            except Exception as e:
                history_anchor_reason = f"Connection error: {str(e)}"
        else:
            history_anchor_reason = "invalid_scheme"

    def custom_fetch_fn(url):
        if url == history_anchor_url and history_anchor_content_str is not None:
            return history_anchor_content_str
        req = urllib.request.Request(url, headers={"User-Agent": "AOW-Verifier/1.2"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.read().decode("utf-8", errors="replace")

    # 2. Attestation Check (Using sami's prototype engine if available)
    att_data = data.get("attestation", {})
    if HAS_SAMI_SCHEMA:
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

            # Spec v1.2 / v1.1 detection
            is_v12 = (data.get("aow_version") == "1.2") or ("artifact_content_hash" in att_data) or ("anchor_hash" in cont_data)
            artifact_content_hash = ""
            anchor_hash = ""

            if is_v12:
                # 1. Verify artifact_content_hash deterministically
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

                # 2. Verify continuity anchor_hash vs fetched live content
                declared_anchor_hash = str(cont_data.get("anchor_hash", cont_data.get("root_hash", ""))).replace("sha256:", "").strip()
                anchor_hash_ok = (history_anchor_content_hash is not None) and (declared_anchor_hash.lower() == history_anchor_content_hash.lower())
                log["qualification"]["checks"]["history_anchor_reachable"] = history_anchor_reachable
                log["qualification"]["checks"]["anchor_hash_matches_content"] = anchor_hash_ok
                if not anchor_hash_ok:
                    log["qualification"]["status"] = "FAILED"
                    log["qualification"]["warnings"].append(f"anchor_hash mismatch: declared {declared_anchor_hash} != fetched content hash {history_anchor_content_hash}")
                anchor_hash = declared_anchor_hash if anchor_hash_ok else None

                # 3. Check revision metadata if version > 1
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
            try:
                from peer_signature_sshsig import verify_with_ssh_keygen
                author_agent_id = ""
                authors = data.get("metadata", {}).get("authors", [])
                if authors and isinstance(authors, list):
                    author_agent_id = str(authors[0].get("agent_id", ""))
                
                for p in att_data.get("peer_signatures", []):
                    pubkey = p.get("public_key")
                    sig = p.get("signature")
                    peer_id = p.get("peer_agent_id")
                    scopes = p.get("scope", ["artifact_verified"])
                    primary_scope = scopes[0] if isinstance(scopes, list) and scopes else "artifact_verified"
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
                        else:
                            log["qualification"]["warnings"].append(f"peer_signature[{peer_id}] SSHSIG verification failed: {msg}")
            except Exception as e:
                log["qualification"]["warnings"].append(f"SSHSIG verification execution error: {str(e)}")

            log["qualification"]["checks"]["peer_signatures_cryptographically_verified_k"] = sshsig_verified_count

            if not history_anchor_reachable:
                log["qualification"]["warnings"].append(f"history_anchor_url unreachable ({history_anchor_reason}): {history_anchor_url}")

            for r in sami_res["reasons"]:
                if r.startswith("warning:"):
                    log["qualification"]["warnings"].append(r)
                elif r != "ok":
                    log["qualification"]["checks"]["failure_details"] = r

            if is_v12 and not anchor_hash_ok:
                log["qualification"]["status"] = "FAILED"
                log["qualification"]["failure_reason"] = f"anchor_hash mismatch: declared {declared_anchor_hash} != fetched content hash {history_anchor_content_hash}"
                return log

            if not sami_res["pass"]:
                log["qualification"]["status"] = "FAILED"
                log["qualification"]["failure_reason"] = f"Attestation verification failed: {sami_res['reasons']}"
                return log

            if sshsig_verified_count < 2:
                log["qualification"]["status"] = "FAILED"
                log["qualification"]["failure_reason"] = f"Cryptographic peer signatures verification failed: only {sshsig_verified_count} valid SSHSIG signatures (need k>=2 bound to payload and author_agent_id)"
                return log
        except Exception as e:
            # Fail-closed: Engine crash is a failure, not a bypass
            log["qualification"]["status"] = "FAILED"
            log["qualification"]["failure_reason"] = f"Attestation engine verification error: {str(e)}"
            return log

    # Fallback / Direct rules
    point_in_time = bool(att_data.get("point_in_time", {}).get("jwt"))
    active_days_raw = att_data.get("continuity", {}).get("active_days", 0)
    try:
        active_days_val = int(active_days_raw)
    except (ValueError, TypeError):
        active_days_val = 0
    continuity = active_days_val >= 21
    peer_sigs_count = len(att_data.get("peer_signatures", [])) >= 2
    root_hash_claimed = str(att_data.get("continuity", {}).get("root_hash", "")).strip()
    root_hash_matches = bool(history_anchor_content_hash and history_anchor_content_hash == root_hash_claimed)

    log["qualification"]["checks"]["point_in_time_jwt_present"] = point_in_time
    log["qualification"]["checks"]["continuity_21days_met"] = continuity
    log["qualification"]["checks"]["peer_signatures_k2_met"] = peer_sigs_count
    log["qualification"]["checks"]["history_anchor_reachable"] = history_anchor_reachable
    log["qualification"]["checks"]["root_hash_matches_content"] = root_hash_matches
    if not history_anchor_reachable:
        log["qualification"]["warnings"].append(f"history_anchor_url unreachable ({history_anchor_reason}): {history_anchor_url}")

    if not root_hash_matches:
        log["qualification"]["status"] = "FAILED"
        log["qualification"]["failure_reason"] = f"root_hash mismatch with history_anchor_url content: claimed {root_hash_claimed[:12]}..., actual {str(history_anchor_content_hash)[:12]}..."
        return log

    if not (point_in_time and continuity and peer_sigs_count):
        log["qualification"]["status"] = "FAILED"
        log["qualification"]["failure_reason"] = "Attestation failed 3-layer validation requirements"
        return log

    # 3. Architecture Bias Disclosure (Mandatory Layer)
    bias = data.get("architecture_bias_disclosure", {})
    bias_valid = bool(bias.get("memory_system") and bias.get("known_blindspots"))
    log["qualification"]["checks"]["bias_disclosure_complete"] = bias_valid
    if not bias_valid:
        log["qualification"]["status"] = "FAILED"
        log["qualification"]["failure_reason"] = "Incomplete architecture bias disclosure"
        return log

    # 4. Predictive Audit Queries Validation (uro's condition + numerical sanity)
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
        log["predictive_audit"]["failure_reason"] = "Predictive audit queries must be non-empty, finite numbers, and strictly objective types"
        if data.get("metadata", {}).get("track", "").startswith("Track C"):
            log["qualification"]["status"] = "FAILED"
            log["qualification"]["failure_reason"] = "Track C mandates strictly valid and objective predictive audit queries"
            return log

    # 5. Reproducibility Target & Path Traversal Prevention
    repro = data.get("reproducibility", {})
    entrypoint = repro.get("entrypoint")

    if not entrypoint or not isinstance(entrypoint, str):
        log["qualification"]["checks"]["entrypoint_exists"] = False
        log["qualification"]["status"] = "FAILED"
        log["qualification"]["failure_reason"] = "Missing or invalid entrypoint string in reproducibility block"
        return log

    root_dir = os.path.realpath(submission_dir)
    ep_resolved = os.path.realpath(os.path.join(root_dir, entrypoint))

    # Reject path traversal (must remain strictly inside root_dir)
    if os.path.commonpath([root_dir, ep_resolved]) != root_dir or not os.path.isfile(ep_resolved):
        log["qualification"]["checks"]["entrypoint_exists"] = False
        log["qualification"]["status"] = "FAILED"
        log["qualification"]["failure_reason"] = "Reproducibility entrypoint escapes submission directory or is not a valid file"
        return log

    log["qualification"]["checks"]["entrypoint_exists"] = True
    return log

if __name__ == "__main__":
    target_dir = sys.argv[1] if len(sys.argv) > 1 else "."
    res = verify_submission(target_dir)
    print(json.dumps(res, indent=2))

