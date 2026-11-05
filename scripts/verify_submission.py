#!/usr/bin/env python3
"""
AOW Submission Verifier (v1.2)
Integrates sami's Attestation verification engine and uro's Predictive Audit rules.
Emits verification_log.json for automated qualification evaluation.
Includes strict path traversal prevention, fail-closed attestation, and type validation.
"""

import sys, os, json, hashlib, math
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

            log["qualification"]["checks"]["sami_attestation_engine"] = sami_res["pass"]
            for r in sami_res["reasons"]:
                if r.startswith("warning:"):
                    log["qualification"]["warnings"].append(r)
                elif r != "ok":
                    log["qualification"]["checks"]["failure_details"] = r

            if not sami_res["pass"]:
                log["qualification"]["status"] = "FAILED"
                log["qualification"]["failure_reason"] = f"Attestation verification failed: {sami_res['reasons']}"
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

    log["qualification"]["checks"]["point_in_time_jwt_present"] = point_in_time
    log["qualification"]["checks"]["continuity_21days_met"] = continuity
    log["qualification"]["checks"]["peer_signatures_k2_met"] = peer_sigs_count

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

