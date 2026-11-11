"""TRD case gate: fail-closed checks over sources, reviews and claims.

Passing means the required verification workflow is satisfied, NOT proof that
statements are true. Issue order is part of the report contract; keep it stable.
"""
from __future__ import annotations
from pathlib import Path
from .base import (REQUIRED_DIMENSIONS, REVIEWERS, VALID_RISKS, VALID_TYPES, VERSION, _issue,
                   _norm_text, days_since, digest_object, now_utc, review_signature_valid,
                   validate_calculation, verify_file)


def _check_case_header(case, root, case_issues):
    case_id = case.get('case_id')
    if not isinstance(case_id, str) or not case_id.strip():
        _issue(case_issues, 'CASE_ID', 'Case ID is missing', 'BLOCK')
    if not isinstance(case.get('jurisdiction'), str) or not case['jurisdiction'].strip():
        _issue(case_issues, 'JURISDICTION', 'Jurisdiction is missing')
    _artifact, artifact_error = verify_file(root, case.get('artifact', {}))
    if artifact_error:
        _issue(case_issues, 'ARTIFACT_INTEGRITY', artifact_error, 'BLOCK')
    sources = case.get('sources', [])
    claims = case.get('claims', [])
    if not isinstance(sources, list) or not isinstance(claims, list) or not claims:
        _issue(case_issues, 'EMPTY_CASE', 'A nonempty claims array and sources array are required', 'BLOCK')
        sources, claims = [], []
    if len({s.get('id') for s in sources if isinstance(s, dict)}) != len(sources):
        _issue(case_issues, 'SOURCE_IDS', 'Source identifiers must be unique', 'BLOCK')
    if len({c.get('id') for c in claims if isinstance(c, dict)}) != len(claims):
        _issue(case_issues, 'CLAIM_IDS', 'Claim identifiers must be unique', 'BLOCK')
    return case_id, sources, claims


def _check_snapshot(root, source, problems):
    doc, doc_error = verify_file(root, source)
    if doc_error:
        _issue(problems, 'SOURCE_INTEGRITY', doc_error, 'BLOCK')
    elif doc.stat().st_size > 15 * 1024 * 1024:
        _issue(problems, 'SOURCE_SIZE', 'Source >15MB requires a controlled excerpt')
    else:
        try:
            return _norm_text(doc.read_text(encoding='utf-8'))
        except (UnicodeError, OSError):
            _issue(problems, 'SOURCE_TEXT', 'Evidence must have a UTF-8 text snapshot')
    return None


def _check_origin(root, source, max_age_days, problems):
    origin = source.get('origin', {})
    if not isinstance(origin, dict):
        origin = {}
    if origin.get('status') != 'attested' or not all(origin.get(k) for k in ('method', 'checked_by', 'checked_at')):
        _issue(problems, 'ORIGIN', 'Source origin requires a documented external attestation')
        return
    _proof, proof_error = verify_file(root, origin.get('proof', {}))
    if proof_error:
        _issue(problems, 'ORIGIN_PROOF', f'Attestation proof: {proof_error}')
    try:
        age = days_since(origin['checked_at'])
        if age < -1 or age > max_age_days:
            _issue(problems, 'ORIGIN_AGE', 'Source origin attestation is stale or future-dated')
    except (ValueError, TypeError):
        _issue(problems, 'ORIGIN_TIME', 'Origin attestation time must be offset-aware ISO 8601')


def _check_source_metadata(source, max_age_days, problems):
    for key in ('publisher', 'title', 'independence_group', 'source_type'):
        if not isinstance(source.get(key), str) or not source[key].strip():
            _issue(problems, 'SOURCE_METADATA', f'Missing source {key}')
    if source.get('source_type') == 'ai_generated':
        _issue(problems, 'AI_AS_SOURCE', 'AI text cannot be a validating source', 'BLOCK')
    try:
        age = days_since(source['retrieved_at'])
        if age < -1 or age > max_age_days:
            _issue(problems, 'RETRIEVAL_AGE', 'Source snapshot needs a refreshed retrieval review')
    except (ValueError, KeyError, TypeError):
        _issue(problems, 'RETRIEVAL_TIME', 'Source retrieved_at must be offset-aware ISO 8601')


def _check_sources(root, sources_by_id, max_age_days):
    source_issues, source_contents = {}, {}
    for sid, source in sources_by_id.items():
        problems = []
        content = _check_snapshot(root, source, problems)
        if content is not None:
            source_contents[sid] = content
        _check_origin(root, source, max_age_days, problems)
        _check_source_metadata(source, max_age_days, problems)
        source_issues[sid] = problems
    return source_issues, source_contents


def _check_review(name, review, case_id, case_hash, key):
    errors = []
    if review.get('reviewer') != name:
        _issue(errors, 'REVIEW_IDENTITY', f'Reviewer must be {name}', 'BLOCK')
    if review.get('case_id') != case_id or review.get('case_sha256') != case_hash:
        _issue(errors, 'REVIEW_CASE', 'Review is for a different or changed case', 'BLOCK')
    if not review_signature_valid(review, key):
        _issue(errors, 'REVIEW_SIGNATURE', 'Signature missing/invalid or independent key unavailable', 'BLOCK')
    if not all(isinstance(review.get(k), str) and review[k].strip() for k in ('run_id', 'model_id')):
        _issue(errors, 'REVIEW_RUN', 'Independent run and model metadata required')
    if review.get('independent_context') is not True:
        _issue(errors, 'REVIEW_ISOLATION', 'Review must attest independent raw-evidence context')
    try:
        age = days_since(review['reviewed_at'])
        if age < -1 or age > 30:
            _issue(errors, 'REVIEW_AGE', 'Review stale or future dated')
    except (ValueError, KeyError, TypeError):
        _issue(errors, 'REVIEW_TIME', 'Review timestamp invalid')
    return errors


def _check_reviews(reviews, keys, case_id, case_hash):
    per_review = {}
    for name in REVIEWERS:
        review = reviews.get(name)
        if not isinstance(review, dict):
            errors = []
            _issue(errors, 'REVIEW_MISSING', f'{name} independent review is missing')
            per_review[name] = {'review': None, 'issues': errors}
            continue
        per_review[name] = {'review': review, 'issues': _check_review(name, review, case_id, case_hash, keys.get(name))}
    a = per_review['Claude']['review']
    b = per_review['JEV']['review']
    if a and b and (a.get('run_id') == b.get('run_id') or a.get('model_id') == b.get('model_id')):
        for name in REVIEWERS:
            _issue(per_review[name]['issues'], 'REVIEW_NOT_INDEPENDENT', 'Reviewer model IDs and run IDs must differ', 'BLOCK')
    return per_review


def _check_measurement(claim, sources_by_id, problems):
    m = claim.get('measurement', {})
    if not isinstance(m, dict) or not all(m.get(k) for k in ('raw_record_source_id', 'measured_at', 'instrument', 'unit', 'calibration_status')):
        _issue(problems, 'MEASUREMENT', 'Original record, timestamp, instrument, units and calibration status required')
        return
    if m['raw_record_source_id'] not in sources_by_id:
        _issue(problems, 'RAW_RECORD', 'Original measurement source missing', 'BLOCK')
    try:
        days_since(m['measured_at'])
    except (ValueError, TypeError):
        _issue(problems, 'MEASUREMENT_TIME', 'Measurement timestamp must include time zone')


def _check_claim_shape(claim, cid, sources_by_id, problems):
    risk, ctype = claim.get('risk'), claim.get('type')
    if risk not in VALID_RISKS or ctype not in VALID_TYPES:
        _issue(problems, 'CLAIM_SCHEMA', 'Invalid risk or claim type', 'BLOCK')
    if not isinstance(cid, str) or not cid.strip():
        _issue(problems, 'CLAIM_ID', 'Claim ID missing', 'BLOCK')
    if not isinstance(claim.get('text'), str) or not claim['text'].strip():
        _issue(problems, 'CLAIM_TEXT', 'Claim text missing', 'BLOCK')
    if not isinstance(claim.get('context'), str) or not claim['context'].strip():
        _issue(problems, 'CLAIM_CONTEXT', 'Claim must identify applicable context and time')
    if claim.get('known_conflict'):
        _issue(problems, 'KNOWN_CONFLICT', 'Unresolved contradictory evidence declared', 'BLOCK')
    if ctype == 'observation':
        _check_measurement(claim, sources_by_id, problems)
    if ctype == 'calculation':
        err = validate_calculation(claim.get('calculation'))
        if err:
            _issue(problems, 'CALCULATION', err, 'BLOCK')


def _citation_group(citation, ctx, seen_source, problems):
    """Check one citation; return its independence group when it counts toward corroboration."""
    sources_by_id, source_issues, source_contents = ctx
    if not isinstance(citation, dict):
        _issue(problems, 'CITATION_SCHEMA', 'Citation must be an object', 'BLOCK')
        return None
    sid = citation.get('source_id')
    if sid in seen_source:
        _issue(problems, 'DUPLICATE_CITATION', 'Repeated source citation does not increase corroboration')
        return None
    seen_source.add(sid)
    src = sources_by_id.get(sid)
    if not src:
        _issue(problems, 'SOURCE_MISSING', 'Referenced source does not exist', 'BLOCK')
        return None
    for p in source_issues.get(sid, []):
        _issue(problems, f'SOURCE_{p["code"]}', f'{sid}: {p["message"]}', p['severity'])
    return _citation_support_group(citation, sid, src, source_issues, source_contents, problems)


def _citation_support_group(citation, sid, src, source_issues, source_contents, problems):
    if citation.get('support') != 'direct':
        _issue(problems, 'INDIRECT_SUPPORT', 'Direct support is mandatory; interpretation is reviewed separately')
        return None
    quote = citation.get('exact_quote', '')
    if not isinstance(quote, str) or len(quote.strip()) < 8:
        _issue(problems, 'EXACT_QUOTE', 'A substantive exact quote is required')
        return None
    if sid not in source_contents or _norm_text(quote) not in source_contents[sid]:
        _issue(problems, 'QUOTE_NOT_FOUND', 'Exact source excerpt is not in the fingerprinted evidence snapshot', 'BLOCK')
        return None
    if not citation.get('locator'):
        _issue(problems, 'LOCATOR', 'Page/line/table locator required')
        return None
    if source_issues.get(sid):
        return None
    publisher = str(src.get('publisher', '')).strip().casefold()
    group = str(src.get('independence_group', '')).strip().casefold()
    return group if publisher and group else None


def _check_citations(claim, ctx, problems):
    citations = claim.get('citations', [])
    if not isinstance(citations, list):
        citations = []
    required = 3 if claim.get('risk') in ('high', 'critical') else 2
    distinct, seen_source = set(), set()
    for citation in citations:
        group = _citation_group(citation, ctx, seen_source, problems)
        if group:
            distinct.add(group)
    if len(distinct) < required:
        _issue(problems, 'CORROBORATION', f'{required} independent authenticated sources required; {len(distinct)} eligible')
    return citations


def _check_assessment(name, assessment, problems):
    verdict = assessment.get('verdict')
    if verdict != 'supported':
        _issue(problems, 'REVIEW_VERDICT', f'{name} verdict: {verdict}', 'BLOCK' if verdict in ('contradicted', 'unsupported') else 'HOLD')
    for dimension in REQUIRED_DIMENSIONS:
        if assessment.get(dimension) != 'pass':
            _issue(problems, 'REVIEW_DIMENSION', f'{name}: {dimension} is not pass')
    if assessment.get('contradictions') != 'none':
        _issue(problems, 'REVIEW_CONTRADICTIONS', f'{name} unresolved contradiction', 'BLOCK')
    if not isinstance(assessment.get('reason'), str) or len(assessment['reason'].strip()) < 20:
        _issue(problems, 'REVIEW_REASON', f'{name} needs reasoned evidence assessment')


def _apply_reviews(cid, per_review, problems):
    for name in REVIEWERS:
        state = per_review[name]
        if state['issues']:
            for issue in state['issues']:
                _issue(problems, issue['code'], f'{name}: {issue["message"]}', issue['severity'])
            continue
        match = [x for x in state['review'].get('claims', []) if isinstance(x, dict) and x.get('id') == cid]
        if len(match) != 1:
            _issue(problems, 'REVIEW_CLAIM_MISSING', f'{name} has no unique claim assessment')
            continue
        _check_assessment(name, match[0], problems)


def _check_claim(claim, ctx, per_review):
    cid = claim.get('id', '(missing ID)')
    problems = []
    _check_claim_shape(claim, cid, ctx[0], problems)
    citations = _check_citations(claim, ctx, problems)
    _apply_reviews(cid, per_review, problems)
    status = 'BLOCK' if any(i['severity'] == 'BLOCK' for i in problems) else ('HOLD' if problems else 'PASS')
    cited = sorted(str(c.get('source_id')) for c in citations if isinstance(c, dict))
    return {'claim_id': cid, 'risk': claim.get('risk'), 'status': status, 'issues': problems, 'cited_sources': cited}


def _report(case_id, case_hash, case_issues, results, per_review):
    blocked = any(x['severity'] == 'BLOCK' for x in case_issues) or any(x['status'] == 'BLOCK' for x in results)
    held = case_issues or any(x['status'] != 'PASS' for x in results)
    status = 'BLOCK' if blocked else ('HOLD' if held else 'PASS')
    signatures = {name: bool(per_review[name]['review'] and not any(i['code'] == 'REVIEW_SIGNATURE' for i in per_review[name]['issues']))
                  for name in REVIEWERS}
    return {'trd_version': VERSION, 'case_id': case_id, 'case_sha256': case_hash, 'status': status, 'evaluated_at': now_utc(),
            'claim_counts': {s: sum(r['status'] == s for r in results) for s in ('PASS', 'HOLD', 'BLOCK')},
            'case_issues': case_issues, 'claims': results,
            'interpretation': 'PASS verifies the configured evidence-review process, not the metaphysical truth of claims.',
            'reviewer_signatures': signatures}


def check_case(case, root, reviews=None, max_age_days=365, keys=None):
    """Return the full inspectable result; no online claims or automatic web-authentication.

    Source origin is *attested* by audit evidence. A truthful statement cannot be
    certified by code alone. Cryptographic reviewer signatures are mandatory.
    """
    reviews = reviews or {}
    keys = keys or {}
    root = Path(root).resolve()
    if not isinstance(case, dict):
        raise ValueError('case must be a JSON object')
    case_issues = []
    case_id, sources, claims = _check_case_header(case, root, case_issues)
    sources_by_id = {s.get('id'): s for s in sources if isinstance(s, dict)}
    source_issues, source_contents = _check_sources(root, sources_by_id, max_age_days)
    case_hash = digest_object(case)
    per_review = _check_reviews(reviews, keys, case_id, case_hash)
    ctx = (sources_by_id, source_issues, source_contents)
    results = []
    for claim in claims:
        if not isinstance(claim, dict):
            _issue(case_issues, 'CLAIM_TYPE', 'Every claim must be an object', 'BLOCK')
            continue
        results.append(_check_claim(claim, ctx, per_review))
    return _report(case_id, case_hash, case_issues, results, per_review)
