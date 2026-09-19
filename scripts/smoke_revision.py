"""Shared smoke CLI setup and deployment admission checks."""
import argparse
import os
import sys


def parse_backend_args():
    _PROD_URL = "https://pi-dev-ops-production.up.railway.app"

    parser = argparse.ArgumentParser(description="Pi CEO smoke test")
    parser.add_argument("--url", default="http://127.0.0.1:7777", help="Server base URL")
    parser.add_argument("--password", default=os.environ.get("TAO_PASSWORD", ""), help="Server password")
    parser.add_argument("--target", choices=["prod", "local"], default="local",
                        help="'prod' hits the Railway production URL")
    parser.add_argument("--emit-metrics", action="store_true",
                        help="Write results to .harness/post-deploy-metrics/ JSONL")
    parser.add_argument("--agent-sdk", action="store_true",
                        help="Run SDK path verification checks (RA-575); requires server running")
    parser.add_argument("--expected-sha", default=os.environ.get("EXPECTED_SHA", ""),
                        help="Full deployed git SHA; required for production smoke")
    parser.add_argument("--deployment-timeout", type=float, default=180,
                        help="Seconds to wait for the expected deployment")
    args = parser.parse_args()

    # --target=prod overrides --url and flags prod mode (skips local FS checks)
    prod_mode = args.target == "prod"
    if prod_mode and not args.expected_sha:
        parser.error("--expected-sha is required for production smoke")
    if prod_mode and args.url == "http://127.0.0.1:7777":
        args.url = _PROD_URL

    return args


def parse_e2e_args():
    parser = argparse.ArgumentParser(description="Full-stack smoke test (RA-1154)")
    parser.add_argument("--mode", choices=["horizontal", "vertical", "full"], default="full")
    parser.add_argument("--url", default=os.environ.get("DASHBOARD_URL", "https://pi-dev-ops.vercel.app"))
    parser.add_argument("--password", default=os.environ.get("DASHBOARD_PASSWORD", ""))
    parser.add_argument("--expected-sha", default=os.environ.get("EXPECTED_SHA", ""),
                        help="Full git SHA required for both deployed runtimes")
    parser.add_argument("--deployment-timeout", type=float, default=180)
    return parser.parse_args()


def verify_backend_revision(get, args, wait_for_revision) -> bool:
    headers = {"Cache-Control": "no-cache"}
    if args.password:
        # Public health deliberately omits deployment identity until authenticated.
        headers["Authorization"] = f"Bearer {args.password}"
    try:
        revision = wait_for_revision(
            lambda: get("/health", headers=headers),
            args.expected_sha, timeout=args.deployment_timeout,
        )
    except (ValueError, TimeoutError) as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        return False
    print(f"Verified backend deployment revision: {revision}")
    return True


def verify_e2e_revisions(session, args, wait_for_revision) -> bool:
    try:
        frontend_revision = wait_for_revision(
            lambda: session.request("GET", "/api/revision", timeout=10,
                                    extra_headers={"Cache-Control": "no-cache"}),
            args.expected_sha, timeout=args.deployment_timeout,
        )
        if not session.login(args.password):
            print("[fatal] Login failed before backend revision verification", file=sys.stderr)
            return False
        backend_revision = wait_for_revision(
            lambda: session.request("GET", "/api/pi-ceo/health", timeout=10,
                                    extra_headers={"Cache-Control": "no-cache"}),
            args.expected_sha, timeout=args.deployment_timeout,
        )
    except (ValueError, TimeoutError) as exc:
        print(f"[fatal] {exc}", file=sys.stderr)
        return False
    print(f"Verified deployment revisions: frontend={frontend_revision} backend={backend_revision}")

    return True


def report_totals(all_runs) -> int:
    total_passed = sum(r.passed_count for r in all_runs)
    total_failed = sum(r.failed_count for r in all_runs)

    print()
    print("═" * 60)
    print(f"TOTAL: {total_passed} passed · {total_failed} failed")
    print("═" * 60)

    return 0 if total_failed == 0 else 1
