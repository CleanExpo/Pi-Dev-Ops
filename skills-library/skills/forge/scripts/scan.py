#!/usr/bin/env python3
"""forge scanner — OWASP-mapped static checks over a skill directory → AI-BOM JSON.
scan-exempt: pattern-definitions

usage: scan.py <skill-dir> [--bom-out <path>]
exit 0 = PASS (registerable), exit 1 = FAIL (stays quarantined), exit 2 = usage,
exit 3 = CANNOT DETERMINE (the scan did not run; NOT a verdict).

Exit 3 exists because 1 used to mean both "this skill failed" and "the scanner
broke", and a caller cannot tell those apart — so it records the skill as bad.
Two live paths produced it: a directory that does not exist (os.walk yields
nothing, so all six content checks were marked PASS and an AI-BOM was written
asserting the skill was clean of secrets), and `--bom-out` as the final argument
(IndexError). "I could not look" must never read as "nothing is wrong".

Checks (IDs map to threat-model.md):
  SEC-SECRET      planted credentials (flags file:line, never prints the match)
  SEC-DESTRUCT    destructive default actions without a human gate
  SEC-EXEC        execution of attacker-controllable/fetched content
  SEC-INJECT      injected agent-directed instructions in references/assets
  SEC-SCOPE       frontmatter tool scope vs body usage (least privilege)
  QA-FRONTMATTER  name matches dir, description present
  QA-TESTS        assertion-less tests, TODO/placeholder stubs, scope-narrowing
"""
import json, os, re, sys, datetime

SECRETS = [
    r"sk-ant-[A-Za-z0-9_-]{8,}", r"sk-proj-[A-Za-z0-9_-]{8,}", r"sk-ant-oat[A-Za-z0-9_-]*",
    r"AIza[0-9A-Za-z_-]{30,}", r"ghp_[0-9A-Za-z]{20,}", r"xox[bp]-[0-9A-Za-z-]{10,}",
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----", r"Bearer [A-Za-z0-9_\-\.]{25,}",
]
DESTRUCT = [
    (r"rm\s+-rf?\s+(?!\$TMP|/tmp|\"\$\{?SCRATCH)", "recursive delete"),
    (r"git\s+push\s+.*--force", "force push"),
    (r"\bDROP\s+(TABLE|DATABASE)\b", "SQL drop"),
    (r"\bDELETE\s+FROM\b(?!.*WHERE)", "unbounded SQL delete"),
    (r"vercel\s+.*\s(rm|remove)\b", "resource removal"),
]
HUMAN_GATE = re.compile(r"human[- ](gate|approv|execute)|founder (merges|executes|approv)|ask the (user|human)|never run this automatically", re.I)
EXEC_UNTRUSTED = [
    (r"curl[^\n|]*\|\s*(ba)?sh", "curl piped to shell"),
    (r"\beval\s*\(", "eval()"),
    (r"\bexec\s*\(", "exec()"),
    (r"os\.system\s*\(\s*[a-z_]*(fetch|response|content|body|html|page)", "shell on fetched content"),
]
# Widened 31/08/2026. The previous pattern required the qualifier and the noun to be
# ADJACENT — `ignore (all|any|previous|prior) (instructions|context)` — so it matched
# "ignore all instructions" but NOT "ignore all previous instructions", which is the
# canonical prompt-injection string. Also missed "ignore any prior context", "ignore the
# above rules" and "disregard prior". Found by the first test ever written against this
# scanner; validated against 3 prose controls that must NOT match ("please ignore the
# warnings in the previous section", "the parser will ignore blank lines").
INJECT = re.compile(
    r"(ignore\s+(all\s+|any\s+|the\s+)?(previous\s+|prior\s+|preceding\s+|above\s+)?"
    r"(instructions|context|rules|prompts?)"
    r"|you are now|AI AGENT\s*:|disregard (the )?(above|system|previous|prior))", re.I)
SCOPE_NEEDS = {"Bash": r"```bash|\bBash\b tool|run |execute ", "Write": r"\bWrite\b|create .*file", "Edit": r"\bEdit\b"}
NARROWING = re.compile(r"\b(for now|only handles|just a stub|placeholder|TODO|FIXME|skipped for)\b", re.I)


def walk(d):
    for root, dirs, files in os.walk(d):
        dirs[:] = [x for x in dirs if x not in (".git", "node_modules", "__pycache__")]
        for f in files:
            yield os.path.join(root, f)


def main():
    if len(sys.argv) < 2:
        print(__doc__); return 2
    skill_dir = os.path.abspath(sys.argv[1])
    # Fail closed and DISTINGUISHABLY. Without this, every check below reports PASS over
    # an empty walk and the caller banks a clean security result for a path that is not
    # there. A loop over a manifest of skills absorbs every typo and every moved skill.
    if not os.path.isdir(skill_dir):
        print(f"CANNOT DETERMINE  {os.path.basename(skill_dir)}: not a directory ({skill_dir})")
        return 3
    if "--bom-out" in sys.argv:
        i = sys.argv.index("--bom-out")
        if i + 1 >= len(sys.argv):
            print("CANNOT DETERMINE: --bom-out given with no path")
            return 3
        bom_out = sys.argv[i + 1]
    else:
        bom_out = os.path.join(skill_dir, "ai-bom.json")
    checks, name, desc, tools = [], os.path.basename(skill_dir), "", ""

    sk = os.path.join(skill_dir, "SKILL.md")
    # errors="replace" to match the walk() reads below. Most of this corpus is CRLF and
    # Windows-authored, so one smart quote in a non-UTF-8 encoding would otherwise raise
    # UnicodeDecodeError and — before exit 3 existed — read as a failed skill.
    body = open(sk, encoding="utf-8", errors="replace").read() if os.path.exists(sk) else ""
    m = re.search(r"^name:\s*(\S+)", body, re.M); fm_name = m.group(1) if m else ""
    m = re.search(r"^description:\s*(.+)$", body, re.M); desc = (m.group(1) if m else "").strip()
    m = re.search(r"^allowed-tools:\s*(.+)$", body, re.M); tools = (m.group(1) if m else "").strip()

    def add(cid, status, detail=""):
        checks.append({"id": cid, "status": status, "detail": detail})

    # QA-FRONTMATTER
    if not body: add("QA-FRONTMATTER", "FAIL", "no SKILL.md")
    elif fm_name != name: add("QA-FRONTMATTER", "FAIL", f"frontmatter name != dir name ({fm_name!r})")
    elif not desc: add("QA-FRONTMATTER", "FAIL", "missing description")
    else: add("QA-FRONTMATTER", "PASS")

    sec_hits = {"SEC-SECRET": [], "SEC-DESTRUCT": [], "SEC-EXEC": [], "SEC-INJECT": [], "QA-TESTS": []}
    exempted = []
    for path in walk(skill_dir):
        if os.path.basename(path) == "ai-bom.json" or not re.search(r"\.(md|py|sh|js|ts|txt|ya?ml|json|html)$", path):
            continue
        try:
            txt = open(path, errors="replace").read()
        except Exception:
            continue
        rel = os.path.relpath(path, skill_dir)
        # Loud exemption for pattern-definition files (e.g. this scanner's own source).
        # Recorded in the AI-BOM so the human sees every exemption at promotion time.
        if "scan-exempt: pattern-definitions" in txt[:400]:
            exempted.append(rel)
            continue
        for pat in SECRETS:
            for mm in re.finditer(pat, txt):
                line = txt[:mm.start()].count("\n") + 1
                sec_hits["SEC-SECRET"].append(f"{rel}:{line} (match REDACTED)")
        for pat, label in DESTRUCT:
            for mm in re.finditer(pat, txt):
                ctx = txt[max(0, mm.start()-200):mm.end()+200]
                if not HUMAN_GATE.search(ctx):
                    sec_hits["SEC-DESTRUCT"].append(f"{rel}: {label} without human gate")
        for pat, label in EXEC_UNTRUSTED:
            if re.search(pat, txt):
                sec_hits["SEC-EXEC"].append(f"{rel}: {label}")
        if re.search(r"references/|assets/|fixtures/|\.html$", path.replace(os.sep, "/")) and INJECT.search(txt):
            sec_hits["SEC-INJECT"].append(f"{rel}: agent-directed instruction in content file")
        if re.search(r"(^|_|/)test", rel) and rel.endswith(".py"):
            if "def test" in txt and not re.search(r"^\s*assert\b|\.assert[A-Z]|pytest\.raises", txt, re.M):
                sec_hits["QA-TESTS"].append(f"{rel}: test without assertions")
            if NARROWING.search(txt):
                sec_hits["QA-TESTS"].append(f"{rel}: scope-narrowing/TODO language")

    for cid, hits in sec_hits.items():
        add(cid, "FAIL" if hits else "PASS", "; ".join(hits[:5]))

    # SEC-SCOPE
    declared = {t.strip() for t in tools.split(",") if t.strip()}
    used = {t for t, pat in SCOPE_NEEDS.items() if re.search(pat, body)}
    missing = used - declared if declared else set()
    add("SEC-SCOPE", "FAIL" if (declared and missing) else "PASS",
        f"body implies {sorted(missing)} not declared" if missing else "")

    verdict = "PASS" if all(c["status"] == "PASS" for c in checks) else "FAIL"
    bom = {
        "bomFormat": "AI-BOM/CycloneDX-style", "specVersion": "1.0",
        "generated_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "component": {"name": name, "purpose": desc, "declared_tools": sorted(declared)},
        "scan": {"checks": checks, "verdict": verdict, "exempted_files": exempted},
        "threat_note": "Static scan only; runtime behaviour gated by eval + human promotion.",
    }
    for k in ("bomFormat", "specVersion", "generated_utc", "component", "scan", "threat_note"):
        assert k in bom  # minimal schema self-validation
    with open(bom_out, "w") as f:
        json.dump(bom, f, indent=1)
    print(f"{verdict}  {name}: " + ", ".join(f"{c['id']}={c['status']}" for c in checks))
    if exempted:
        print(f"  NOTE exempted pattern-definition files (verify at promotion): {exempted}")
    for c in checks:
        if c["status"] == "FAIL":
            print(f"  FAIL {c['id']}: {c['detail']}")
    return 0 if verdict == "PASS" else 1

if __name__ == "__main__":
    # Any unhandled exception is "the scanner broke", never "the skill is bad".
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        import traceback
        traceback.print_exc()
        print("CANNOT DETERMINE: the scanner raised; this is not a verdict on the skill")
        sys.exit(3)
