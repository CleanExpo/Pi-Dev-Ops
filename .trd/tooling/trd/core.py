"""TRD deterministic, fail-closed evidence gate. Python standard library only.

Passing means the required verification workflow is satisfied, NOT proof that
statements are true. Trust rests in independent sources and external reviewers.

This module is the stable import surface; the code lives in base, checks and legacy.
"""
from .base import (IGNORE_DIRS, LEGACY_EXTENSIONS, REQUIRED_DIMENSIONS, REVIEWERS, VALID_RISKS,
                   VALID_TYPES, VERSION, canonical_bytes, days_since, digest_bytes, digest_object,
                   now_utc, read_json, review_signature_valid, safe_path, sha256_file, sign_review,
                   validate_calculation, verify_file)
from .checks import check_case
from .legacy import backfill, inventory

__all__ = [
    'IGNORE_DIRS', 'LEGACY_EXTENSIONS', 'REQUIRED_DIMENSIONS', 'REVIEWERS', 'VALID_RISKS',
    'VALID_TYPES', 'VERSION', 'backfill', 'canonical_bytes', 'check_case', 'days_since',
    'digest_bytes', 'digest_object', 'inventory', 'now_utc', 'read_json',
    'review_signature_valid', 'safe_path', 'sha256_file', 'sign_review',
    'validate_calculation', 'verify_file',
]
