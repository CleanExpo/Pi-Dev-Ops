"""CLI for TRD. No network calls; research/authenticity are not faked."""
import argparse
import json
import os
import sys
from pathlib import Path
from .core import backfill, check_case, digest_object, inventory, read_json, sign_review, VERSION

GITIGNORE = '# Raw evidence may contain private customer information\nevidence/\nreviews/\nresults/\nlegacy/\n'
REVIEW_MODES = {
    'Claude': 'Analyse source authority, source-to-claim entailment, measured values, current applicability and hidden assumptions.',
    'JEV': 'Independently challenge every claim using only the raw case and independent source snapshots. Seek counter-evidence, contradictions, shared source ancestry and false precision.',
}


def write_json(path, value):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def require_secret(reviewer):
    return os.environ.get('TRD_CLAUDE_REVIEW_KEY' if reviewer == 'Claude' else 'TRD_JEV_REVIEW_KEY', '')


def build_parser():
    parser = argparse.ArgumentParser(description='TRD v%s: truth, research and delivery gate' % VERSION)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('init', help='Create an isolated .trd workspace (does not modify production configuration)')
    p.add_argument('root')
    p = sub.add_parser('inventory', help='Fingerprint and queue existing reports/documents, without marking content verified')
    p.add_argument('root')
    p = sub.add_parser('backfill', help='Extract unverified passage candidates from existing documents')
    p.add_argument('root')
    p = sub.add_parser('packets', help='Generate isolated evidence-first instructions for Claude and JEV')
    p.add_argument('case')
    p.add_argument('--root', required=True)
    p.add_argument('--out', required=True)
    p = sub.add_parser('sign-review', help='Trusted signer only; secrets MUST NOT be exposed to AI agents')
    p.add_argument('review')
    p.add_argument('--out', required=True)
    p = sub.add_parser('gate', help='Fail-closed quality gate; exit 0=PASS, 2=HOLD, 3=BLOCK')
    p.add_argument('case')
    p.add_argument('--root', required=True)
    p.add_argument('--reviews', required=True, help='Directory containing Claude.json and JEV.json')
    p.add_argument('--out', required=True)
    p.add_argument('--max-age-days', type=int, default=365)
    return parser


def cmd_init(args):
    root = Path(args.root).resolve()
    for folder in ['cases', 'evidence', 'reviews', 'results', 'legacy']:
        (root / '.trd' / folder).mkdir(parents=True, exist_ok=True)
    gitignore = root / '.trd' / '.gitignore'
    if not gitignore.exists():
        gitignore.write_text(GITIGNORE, encoding='utf-8')
    print('Initialised:', root / '.trd')


def cmd_inventory(args):
    value = inventory(args.root)
    out = Path(args.root).resolve() / '.trd' / 'legacy' / 'inventory.json'
    write_json(out, value)
    print(f'UNREVIEWED inventory: {len(value["files"])} files -> {out}')


def cmd_backfill(args):
    value = backfill(args.root)
    out = Path(args.root).resolve() / '.trd' / 'legacy' / 'candidate_queue.json'
    write_json(out, value)
    print(f'Backfill queue: {len(value["files"])} files, {value["candidate_count"]} unverified passages -> {out}')


def _packet(reviewer, case, packet_hash, root):
    template_claims = [{'id': c['id'], 'verdict': 'uncertain', 'authority': 'fail', 'authentication': 'fail', 'accuracy': 'fail',
                        'realism': 'fail', 'currency': 'fail', 'contradictions': 'unknown', 'reason': 'Explain the evidence and uncertainty.'}
                       for c in case.get('claims', [])]
    return {'reviewer': reviewer, 'case_id': case.get('case_id'), 'case_sha256': packet_hash, 'case': case,
            'review_instructions': REVIEW_MODES[reviewer],
            'required': 'For every claim return verdict, authority, authentication, accuracy, realism, currency, contradictions, and substantive reason.',
            'isolation': 'Do NOT read the other reviewer output. Do not assert source authenticity based merely on a URL or file hash. Read each local evidence snapshot from the supplied project root.',
            'project_root': str(Path(root).resolve()),
            'review_template': {'case_id': case.get('case_id'), 'case_sha256': packet_hash, 'reviewer': reviewer,
                                'run_id': '', 'model_id': '', 'independent_context': True, 'reviewed_at': '',
                                'claims': template_claims}}


def cmd_packets(args):
    case = read_json(args.case)
    packet_hash = digest_object(case)
    target = Path(args.out)
    for reviewer in ('Claude', 'JEV'):
        write_json(target / (reviewer + '.packet.json'), _packet(reviewer, case, packet_hash, args.root))
    print('Review packets created; reviews have NOT been executed or approved:', target)


def cmd_sign_review(args):
    payload = read_json(args.review)
    reviewer = payload.get('reviewer')
    if reviewer not in ('Claude', 'JEV'):
        raise ValueError('reviewer must be Claude or JEV')
    signed = sign_review(payload, require_secret(reviewer))
    write_json(args.out, signed)
    print('Signed attestation from trusted review runner:', args.out)


def cmd_gate(args):
    case = read_json(args.case)
    reviews = {}
    for name in ('Claude', 'JEV'):
        target = Path(args.reviews) / (name + '.json')
        if target.is_file():
            reviews[name] = read_json(target)
    report = check_case(case, args.root, reviews, args.max_age_days,
                        {name: require_secret(name) for name in ('Claude', 'JEV')})
    write_json(args.out, report)
    print('TRD GATE:', report['status'], '| claims', report['claim_counts'], '| report', args.out)
    for r in report['claims']:
        if r['status'] != 'PASS':
            print(' -', r['claim_id'], r['status'], ':', ', '.join(sorted({i['code'] for i in r['issues']})))
    sys.exit({'PASS': 0, 'HOLD': 2, 'BLOCK': 3}[report['status']])


COMMANDS = {'init': cmd_init, 'inventory': cmd_inventory, 'backfill': cmd_backfill,
            'packets': cmd_packets, 'sign-review': cmd_sign_review, 'gate': cmd_gate}


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        COMMANDS[args.command](args)
    except (ValueError, OSError, json.JSONDecodeError, KeyError, TypeError) as e:
        print('TRD ERROR (fail closed):', e, file=sys.stderr)
        sys.exit(3)


if __name__ == '__main__':
    main()
