"""TRD deterministic, fail-closed evidence gate. Python standard library only.

Passing means the required verification workflow is satisfied, NOT proof that
statements are true. Trust rests in independent sources and external reviewers.
"""
# Shared primitives: hashing, safe paths, signing and arithmetic checks.
from __future__ import annotations
import datetime as dt
import hashlib
import hmac
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

VERSION = '1.0.0'
VALID_RISKS = {'routine', 'high', 'critical'}
VALID_TYPES = {'observation', 'calculation', 'quotation', 'summary', 'interpretation', 'recommendation'}
REVIEWERS = ('Claude', 'JEV')
REQUIRED_DIMENSIONS = ('authority', 'authentication', 'accuracy', 'realism', 'currency')
IGNORE_DIRS = {'.git', '.trd', 'node_modules', '.venv', 'venv', '__pycache__', '.next', 'dist', 'build', '.cache'}
LEGACY_EXTENSIONS = {'.md', '.txt', '.rst', '.html', '.htm', '.pdf', '.docx', '.csv', '.json', '.xlsx', '.pptx'}


def canonical_bytes(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode('utf-8')


def digest_bytes(data):
    return hashlib.sha256(data).hexdigest()


def digest_object(obj):
    return digest_bytes(canonical_bytes(obj))


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def safe_path(root, relative):
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise ValueError('Expected a nonempty relative path')
    base = Path(root).resolve()
    value = (base / relative).resolve()
    try:
        value.relative_to(base)
    except ValueError:
        raise ValueError('File path escapes project root') from None
    if not value.is_file():
        raise ValueError('Referenced file does not exist')
    return value


def verify_file(root, entry, path_key='path', hash_key='sha256'):
    try:
        if not isinstance(entry, dict):
            return None, 'expected file fingerprint object'
        target = safe_path(root, entry.get(path_key))
        expected = entry.get(hash_key, '')
        if not re.fullmatch(r'[0-9a-f]{64}', expected):
            return None, f'missing/invalid {hash_key}'
        if not hmac.compare_digest(sha256_file(target), expected):
            return None, 'content fingerprint mismatch'
        return target, None
    except (ValueError, TypeError, OSError) as e:
        return None, str(e)


def read_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def now_utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def days_since(date_text):
    parsed = dt.datetime.fromisoformat(date_text.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('timestamp must include timezone')
    return (dt.datetime.now(dt.timezone.utc) - parsed.astimezone(dt.timezone.utc)).total_seconds() / 86400


def sign_review(payload, key):
    if not isinstance(key, str) or len(key) < 32:
        raise ValueError('A secret of at least 32 characters is required')
    review = dict(payload)
    review.pop('signature', None)
    review['signature'] = hmac.new(key.encode('utf-8'), canonical_bytes(review), hashlib.sha256).hexdigest()
    return review


def review_signature_valid(review, key):
    if not key or len(key) < 32:
        return False
    sig = review.get('signature', '')
    if not isinstance(sig, str) or not re.fullmatch('[0-9a-f]{64}', sig):
        return False
    return hmac.compare_digest(sign_review(review, key)['signature'], sig)


def validate_calculation(c):
    if not isinstance(c, dict):
        return 'structured calculation missing'
    operation = c.get('operation')
    try:
        numbers = [Decimal(str(n)) for n in c.get('inputs', [])]
        actual = Decimal(str(c.get('result')))
        tolerance = Decimal(str(c.get('tolerance', '0.000001')))
        if not numbers or tolerance < 0 or any(not n.is_finite() for n in numbers+[actual, tolerance]):
            return 'invalid numeric inputs or tolerance'
        if operation == 'sum':
            calc = sum(numbers)
        elif operation == 'subtract' and len(numbers) == 2:
            calc = numbers[0] - numbers[1]
        elif operation == 'multiply':
            calc = Decimal('1')
            for n in numbers:
                calc *= n
        elif operation == 'divide' and len(numbers) == 2 and numbers[1] != 0:
            calc = numbers[0] / numbers[1]
        else:
            return 'unsupported calculation or input count'
        if abs(calc - actual) > tolerance:
            return f'arithmetic mismatch (calculated {calc}, supplied {actual})'
        if not c.get('unit') or not c.get('method'):
            return 'unit and documented calculation method required'
        return None
    except (InvalidOperation, TypeError, ValueError, ZeroDivisionError):
        return 'malformed numeric calculation'


def _issue(issues, code, message, severity='HOLD'):
    issues.append({'code': code, 'severity': severity, 'message': message})


def _norm_text(s):
    return ' '.join(str(s).split()).casefold()
