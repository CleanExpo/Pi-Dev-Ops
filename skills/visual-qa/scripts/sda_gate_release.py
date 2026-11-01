"""Independent SDA creative, prior-baseline and exact-artifact release holds."""
import math
import hashlib
import json
from pathlib import Path

from sda_gate_core import RUBRIC, strict_json
from sda_gate_media import validate_film
from sda_gate_png import png_dimensions



def _bound_scope_sha(doc):
    """Digest every source-bound capture, not just the hero screenshot."""
    keys = ("schema_version", "deliverable_type", "expected_pages",
            "audit", "screenshots", "candidate_artifact", "film")
    payload = {key: doc.get(key) for key in keys}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _object(value, label, errors):
    if isinstance(value, dict):
        return value
    if value is not None:
        errors.append(label + " must be an object")
    return {}


def _web_candidate(doc, asset, errors):
    candidate = _object(doc.get("candidate_artifact"), "web candidate_artifact", errors)
    verified = asset(candidate.get("file"), candidate.get("sha256"), "web candidate artifact")
    if verified:
        try:
            png_dimensions(verified[1])
        except ValueError as exc:
            errors.append("web candidate artifact is not valid PNG: " + str(exc))


def _review_one(reviews, role, digest, errors):
    review = _object(reviews.get(role), role + " review", errors)
    if review.get("scope_sha256") != digest:
        errors.append(role + ": creative review scope digest missing or mismatched")
    scores = review.get("scores") or {}
    reviewer = review.get("reviewer")
    findings = review.get("findings")
    if (not isinstance(reviewer, str) or not reviewer.strip() or
            not isinstance(findings, list) or not findings or
            not all(isinstance(item, str) and item.strip() for item in findings)):
        errors.append(role + ": reviewer identity and actual critique required")
    if not isinstance(scores, dict) or set(scores) != set(RUBRIC):
        errors.append(role + ": incomplete design rubric")
        return
    values = []
    for category, maximum in RUBRIC.items():
        value = scores[category]
        if (type(value) not in (int, float) or not math.isfinite(value) or
                value < maximum / 2 or value > maximum):
            errors.append(role + ": score out of bounds: " + category)
        else:
            values.append(value)
    if len(values) != len(RUBRIC) or sum(values) < 85:
        errors.append(role + ": score below 85 or invalid")


def _reviews_and_rights(doc, deliverable_type, digest, errors):
    reviews = _object(doc.get("reviews"), "reviews", errors)
    for role in ("sda", "independent_challenger"):
        _review_one(reviews, role, digest, errors)
    sda = reviews.get("sda")
    challenger = reviews.get("independent_challenger")
    # _review_one already records malformed nested review objects. Never
    # attempt dict operations on them or turn a HOLD into a traceback.
    if isinstance(sda, dict) and isinstance(challenger, dict):
        if sda.get("reviewer") == challenger.get("reviewer"):
            errors.append("independent challenger must differ from SDA")
    required = ["creative_direction_approved", "brand_rights_verified", "claims_verified"]
    if deliverable_type == "film":
        required.extend(["audio_rights_verified", "caption_alignment_verified",
                         "actual_full_playback_verified"])
    acceptance = _object(doc.get("acceptance"), "acceptance", errors)
    for key in required:
        if acceptance.get(key) is not True:
            errors.append("acceptance missing: " + key)


def _comparison(doc, deliverable_type, digest, asset, errors):
    baseline = _object(doc.get("approved_baseline"), "approved_baseline", errors)
    baseline_file = asset(baseline.get("file"), baseline.get("sha256"), "prior approved baseline")
    comparison = _object(doc.get("comparison_report"), "comparison_report", errors)
    comparison_bytes = asset(comparison.get("file"), comparison.get("sha256"), "visual comparison")
    if comparison_bytes:
        try:
            compared = strict_json(comparison_bytes[1].decode("utf-8"))
            source_key = "film" if deliverable_type == "film" else "candidate_artifact"
            expected_sha = _object(doc.get(source_key), source_key, errors).get("sha256")
            if (compared.get("baseline_sha256") != baseline.get("sha256") or
                    compared.get("candidate_sha256") != expected_sha or
                    compared.get("scope_sha256") != digest or
                    not isinstance(compared.get("observations"), list) or
                    not compared["observations"] or
                    not all(isinstance(observation, str) and observation.strip()
                            for observation in compared["observations"])):
                raise ValueError("comparison not bound to candidate and approved baseline")
        except (ValueError, AttributeError) as exc:
            errors.append("visual comparison record invalid: " + str(exc))
    return baseline, baseline_file


def _frozen_baseline(root, record, baseline, baseline_file, errors):
    if not record:
        errors.append("separate frozen prior approval record required (--baseline-record)")
        return
    trusted = Path(record).resolve()
    if trusted.is_relative_to(root) or not trusted.is_file():
        errors.append("prior approval record must exist outside candidate evidence directory")
        return
    try:
        frozen = strict_json(trusted.read_text(encoding="utf-8"))
        if (frozen.get("approved_baseline_sha256") != baseline.get("sha256") or
                not frozen.get("approved_by") or not frozen.get("approved_at") or not baseline_file):
            errors.append("prior approval record SHA/approval mismatch")
    except (ValueError, OSError, AttributeError) as exc:
        errors.append("prior approval record invalid: " + str(exc))


def _founder_and_iterations(doc, deliverable_type, digest, errors):
    approval = _object(doc.get("founder_approval"), "founder_approval", errors)
    source_key = "film" if deliverable_type == "film" else "candidate_artifact"
    approved_sha = _object(doc.get(source_key), source_key, errors).get("sha256")
    if (not approved_sha or approval.get("master_sha256") != approved_sha or
            not approval.get("approver") or not approval.get("approved_at")):
        errors.append("exact-candidate founder approval missing or mismatched")
    if approval.get("scope_sha256") != digest:
        errors.append("founder approval scope digest missing or mismatched")
    iteration = doc.get("iteration_count")
    if type(iteration) is not int or iteration < 1:
        errors.append("iteration_count missing or invalid")
    elif iteration > 3:
        errors.append("iteration_count exceeded three; change direction")


def validate_release(doc, root, baseline_record, asset, errors):
    deliverable_type = doc.get("deliverable_type")
    digest = _bound_scope_sha(doc)
    if deliverable_type not in ("web", "film"):
        errors.append("release deliverable_type must be web or film")
    if deliverable_type == "web":
        _web_candidate(doc, asset, errors)
    if deliverable_type == "film":
        validate_film(doc, asset, errors)
    _reviews_and_rights(doc, deliverable_type, digest, errors)
    baseline, baseline_file = _comparison(doc, deliverable_type, digest, asset, errors)
    _frozen_baseline(root, baseline_record, baseline, baseline_file, errors)
    _founder_and_iterations(doc, deliverable_type, digest, errors)
