#!/usr/bin/env python3
"""Autonomy-ladder tier classifier for the PreToolUse gate.

Classifies a pending tool call into L0-L3 (autonomy-ladder skill). The gate
prompts the human ONLY for L3; L0-L2 pass automatically. Replaces the brittle
hardcoded settings.json matcher regex with a tested, reviewable, fail-safe
rule table hardened against the bypass classes an Opus adversary confirmed
(2026-07-06): newline evasion, non-verb-listed deletion/exfil, non-Vercel
deploy tools, DB drops, gh side-effects, shell-piped payloads.

Tiers (higher of reversibility × domain-breadth wins):
  L0/L1 — read or reversible-local
  L2    — outward/reversible (open PR, push feature branch)
  L3    — irreversible / secret / prod / destructive → GATE (human approval)

Invariants:
  * Superset of the legacy matcher — every pattern it gated stays L3.
  * Command string is whitespace-normalized before matching, so newlines /
    line-continuations cannot drop the tier.
  * Fail SAFE — any error → L3. Credential-file references gate regardless of
    verb. Unknown Bash with no danger pattern → L1 (keeps the gate usable).
"""
from __future__ import annotations

import re
from typing import Tuple

# (regex, tier, rule). Matched case-insensitively against the NORMALIZED command
# (single-spaced). Highest matching tier wins.
_BASH_RULES = [
    # ---- L3: filesystem destruction ----
    (r"\brm\s+(-\w*[rf]|[^|;&]*[*?\[]|/|~|\$)", 3, "force/recursive/glob/abs delete"),
    (r"\bfind\b[^|;&]*(-delete|-exec\s+(rm|unlink|shred|truncate))", 3, "find -delete / -exec rm"),
    (r"\bxargs\b[^|;&]*\b(rm|unlink|shred)\b", 3, "xargs rm/unlink/shred"),
    (r"\b(truncate|shred)\b", 3, "truncate/shred (irreversible)"),
    (r"\brsync\b[^|;&]*--delete", 3, "rsync --delete (mirror wipe)"),
    (r"(^|;|&|\|)\s*:?\s*>\s*(?!/dev/null)(?!>)\S", 3, "overwrite/truncate via > redirect"),
    (r"\bcat\s+/dev/null\s*>", 3, "wipe file via /dev/null"),
    (r"\btee\b\s+(?!-a\b)[^-\s]", 3, "tee overwrite"),
    (r"\bdd\b|>\s*/dev/(sd|disk|nvme|rdisk)", 3, "raw disk write"),
    (r"\bmkfs\b|\bmkswap\b", 3, "format filesystem"),
    # ---- L3: git working-tree / history loss ----
    (r"\bgit\s+clean\s+-\w*[fdx]", 3, "git clean (discards untracked)"),
    (r"\bgit\s+reset\s+--hard", 3, "git reset --hard"),
    (r"\bgit\s+(checkout|restore)\s+(--?\s|\.(\s|$)|--staged|--source)", 3, "git discard working changes"),
    (r"\bgit\s+stash\s+(clear|drop)", 3, "git stash discard"),
    (r"\bgit\s+push\b[^|;&]*(--force|--force-with-lease|--mirror|\s-f\b|--delete)", 3, "force/mirror/delete push"),
    (r"\bgit\s+push\s+(prod|production|heroku|live|main-prod)\b", 3, "push to prod remote"),
    (r"\bgit\s+branch\s+-D\b", 3, "force branch delete"),
    # ---- L3: GitHub side-effects ----
    (r"\bgh\s+pr\s+merge", 3, "merge PR to main"),
    (r"\bgh\s+release\s+create", 3, "publish GitHub release"),
    (r"\bgh\s+repo\s+delete", 3, "delete GitHub repo"),
    (r"\bgh\s+workflow\s+run", 3, "trigger CI/deploy workflow"),
    (r"\bgh\s+secret\s+(set|delete)", 3, "write/delete a repo secret"),
    (r"\bgh\s+api\b[^|;&]*(-X|--method)\s*(POST|PUT|PATCH|DELETE)", 3, "mutating GitHub API call"),
    # ---- L3: production / deploy / infra ----
    (r"\b(vercel|netlify|fly|flyctl|wrangler|firebase|serverless|sls|eas|amplify)\b[^|;&]*(deploy|publish|submit|--prod|promote)", 3, "prod deploy"),
    (r"\bterraform\s+(apply|destroy)", 3, "terraform apply/destroy"),
    (r"\bkubectl\s+(apply|delete|replace|patch|scale|drain|cordon)", 3, "kubectl mutate/delete"),
    (r"\bgcloud\b[^|;&]*(deploy|delete|remove)\b", 3, "gcloud deploy/delete"),
    (r"\baws\b[^|;&]*\b(rm|delete|terminate)\b", 3, "AWS resource delete"),
    (r"\b(supabase\s+db\s+push|db\s+reset|prisma\s+migrate\s+(deploy|reset)|alembic\s+downgrade)\b", 3, "prod DB migration"),
    (r"\brailway\s+(up|down|delete|redeploy)", 3, "Railway deploy/teardown"),
    (r"\brailway\s+variables", 3, "read/write prod secrets (Railway)"),
    (r"\b(npm|pnpm|yarn)\s+publish", 3, "publish package"),
    (r"\bdocker\s+push", 3, "push container image"),
    # ---- L3: destructive DB ----
    (r"\b(psql|mysql|sqlite3|mongosh|mongo)\b[^|;&]*\b(drop|truncate|delete\s+from)\b", 3, "destructive SQL"),
    (r"\b(dropDatabase|FLUSHALL|FLUSHDB|dropdb|drop_database)\b", 3, "database drop/flush"),
    (r"\bmysqladmin\b[^|;&]*\bdrop", 3, "mysqladmin drop"),
    (r"\bredis-cli\b[^|;&]*\b(flush|del)\b", 3, "redis flush/del"),
    # ---- L3: secret exfiltration / shell payloads ----
    (r"\b(printenv|env)\b\s*\|", 3, "pipe full environment"),
    (r"\becho\b[^|;&]*\$\w*(KEY|TOKEN|SECRET|PASSWORD)\w*", 3, "echo a secret env var"),
    (r"\|\s*(curl|wget|nc|ncat|telnet)\b", 3, "pipe to network"),
    (r"\b(curl|wget)\b[^|;&]*\|\s*(bash|sh|zsh)\b", 3, "pipe download to shell"),
    (r"\bbase64\s+-d\b[^|;&]*\|\s*(bash|sh|zsh)\b", 3, "pipe decoded payload to shell"),
    (r"\b(scp|sftp)\b", 3, "off-box file copy"),
    (r"api\.stripe\.com|checkout\.stripe\.com", 3, "live financial API (Stripe)"),
    (r"\b1password\b|\bop\s+(read|item|get)\b", 3, "1Password secret read"),
    # ---- L3: runtime destructive one-liners ----
    (r"\b(rmtree|rmSync|unlinkSync|removedirs|os\.remove|shutil\.rmtree|fs\.rm(Sync)?)\b", 3, "runtime recursive delete"),
    (r"\bperl\b[^|;&]*\bunlink\b", 3, "perl unlink"),
    # ---- L3: system / services / privilege ----
    (r"\blaunchctl\s+(unload|bootout|remove|disable)", 3, "stop/disable a service"),
    (r"\b(pkill|killall)\b|\bkill\s+-9", 3, "force-kill process"),
    (r"\b(shutdown|reboot|halt)\b", 3, "power state change"),
    (r"\bsudo\b", 3, "privilege escalation"),
    (r"\bchmod\s+-R\b|\bchmod\s+0?777\b", 3, "broad permission change"),
    # ---- L2: outward / reversible ----
    (r"\bgh\s+pr\s+create", 2, "open a PR"),
    (r"\bgit\s+push\b", 2, "push a branch"),
    (r"\bgh\s+(issue|pr)\s+comment", 2, "post to GitHub"),
]

# Write/Edit destinations that are L3 (credential / config / system paths).
_PATH_RULES = [
    (r"\.(pem|key|p12|pfx)$|id_rsa", 3, "write to a key file"),
    (r"(^|/)(settings|settings\.local)\.json$", 3, "write to Claude settings"),
    (r"/LaunchAgents/|\.plist$", 3, "write a LaunchAgent plist"),
    (r"(^|/)(credentials|secrets)(/|\.|$)", 3, "write to a credentials path"),
    (r"(^|/)\.(netrc|npmrc|pypirc)$", 3, "write to a credential dotfile"),
    (r"(^|/)\.ssh/", 3, "write into ~/.ssh"),
    (r"^/etc/|^/usr/|^/System/", 3, "write to a system path"),
]

# Credential-file token anywhere in a command → L3 regardless of verb (read,
# encode, copy, exfil). Example/sample/template envs are scrubbed out first.
_CRED_TOKEN = re.compile(r"(\.env(\.[\w-]+)?|\.pem|\.key|id_rsa|\.p12|/credentials\b|/secrets\b|\.netrc|\.npmrc|\.pypirc)", re.I)
_CRED_EXAMPLE = re.compile(r"\.env[.-](example|sample|template|dist)", re.I)
_ENV_WRITE = re.compile(r"(^|/)\.env(\.[\w-]+)?$", re.I)
_ENV_WRITE_EXAMPLE = re.compile(r"\.env[.-](example|sample|template|dist)$", re.I)

_BASH_COMPILED = [(re.compile(p, re.IGNORECASE), t, r) for p, t, r in _BASH_RULES]
_PATH_COMPILED = [(re.compile(p, re.IGNORECASE), t, r) for p, t, r in _PATH_RULES]

GATE_TIER = 3  # tiers >= this require human approval


def classify(tool_name: str, tool_input: dict) -> Tuple[int, str]:
    """Return (tier, rule). Never raises for normal input."""
    try:
        if not isinstance(tool_input, dict):
            return 3, "unparseable tool input (fail-safe)"

        if tool_name == "Bash":
            raw = str(tool_input.get("command", ""))
            norm = re.sub(r"\s+", " ", raw)  # collapse newlines/continuations — closes newline-evasion

            # Credential-file access, verb-independent (scrub example/sample envs first).
            scrubbed = _CRED_EXAMPLE.sub("", norm)
            if _CRED_TOKEN.search(scrubbed):
                return 3, "credential-file access"

            best = (1, "bash (no danger pattern)")
            for rx, tier, rule in _BASH_COMPILED:
                if tier > best[0] and rx.search(norm):
                    best = (tier, rule)
                    if tier == 3:
                        break
            return best

        if tool_name in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
            path = str(tool_input.get("file_path", ""))
            if _ENV_WRITE.search(path) and not _ENV_WRITE_EXAMPLE.search(path):
                return 3, "write to a .env file"
            for rx, tier, rule in _PATH_COMPILED:
                if rx.search(path):
                    return tier, rule
            return 1, "local file edit"

        if tool_name in ("Read", "Grep", "Glob", "WebFetch", "WebSearch"):
            return 0, "read-only"

        low = tool_name.lower()
        if any(k in low for k in ("deploy", "delete", "remove", "merge", "publish",
                                   "secret", "rotate", "prod", "eval", "script", "exec", "shell")):
            return 3, f"sensitive MCP/tool: {tool_name}"
        return 2, f"non-bash tool: {tool_name}"
    except Exception as exc:  # pragma: no cover - defensive
        return 3, f"classifier error (fail-safe): {exc}"
