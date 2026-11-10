#!/usr/bin/env python3
"""Capability Passports: one generated, schema-checked record per skill, and a simulated
activation check that reads it.

    capability_passport.py generate [--skills-root P] [--vault-root P] [--state P] [--out P] [--validate]
    capability_passport.py activate <name> [--capability "<what it must do>"] [--max-risk low|medium|high]
                                    [--model M] [--available-models a,b] [--require-tested] [--passports P]
    capability_passport.py record <name> -- <test command ...>
    capability_passport.py validate [--passports P]

A passport is built only from the skill's own SKILL.md (name, description, allowed-tools,
model, owner, capabilities), the router phrases in index.md, HOMES.json, the outside-skill
registry (external-skills.json) and test records this tool wrote itself. It pins the sha256 of
the SKILL.md it was built from, so an edit after generation is caught as STALE_SHA.

`activate` is a SIMULATION. It installs, links, loads and calls nothing; it prints a receipt
saying whether the skill may be used for the request and why not. Exit 0 ALLOW, 3 REFUSE,
2 usage. A model that is not available is refused, never substituted: there is no fallback.

Limits, stated plainly: test records are integrity-checked (exit code, output-log hash, source
hash, recorder), not cryptographically signed, so someone who rewrites both the log and the
record by hand is not detected. Capabilities are exact phrases, not meanings.

Stdlib only. Validation uses a subset JSON Schema validator that refuses any keyword it does
not implement, so a schema can never be silently half-applied.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCHEMA_PATH = HERE.parent / "capability-passport.schema.json"
RECORDER = "capability_passport.record"
RISK_ORDER = {"low": 0, "medium": 1, "high": 2}
PIN_RE = re.compile(r"^[0-9a-f]{40}$")
SKIP_DIRS = {"node_modules", ".git", "deprecated", "in-progress"}
READ_ONLY_TOOLS = {"Read", "Grep", "Glob", "LS", "Skill", "TodoWrite", "AskUserQuestion", "ToolSearch"}
MEDIUM_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit", "WebFetch", "WebSearch", "Agent", "Task", "SendMessage"}


@dataclass
class Roots:
    skills: Path
    vault: Path
    state: Path
    retired: Path

    @classmethod
    def default(cls, skills: Path | None = None, vault: Path | None = None, state: Path | None = None) -> "Roots":
        home = Path.home()
        skills = (skills or home / ".claude" / "skills").resolve()
        return cls(skills=skills, vault=(vault or home / ".claude" / "skill-vault"),
                   state=(state or home / ".local" / "state" / "skill-watch"),
                   retired=skills.parent / "scripts" / "retired-models.txt")


class SchemaError(Exception):
    """The schema uses a keyword this validator does not implement."""


# ---- validation -------------------------------------------------------------------

ANNOTATIONS = {"$schema", "$id", "title", "description"}
TYPES = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None)}


def _is_type(value, name: str) -> bool:
    if name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    return isinstance(value, TYPES[name])


KEYWORDS = {"type", "enum", "const", "required", "properties", "additionalProperties", "items",
            "pattern", "minLength", "minimum"}


def check_schema(schema: dict, where: str = "$") -> None:
    """Every subschema, reached by the instance or not, must use only implemented keywords.
    Checking lazily let `items: {minItems: 1}` pass on an empty array (review P2, 31/10/2026)."""
    unknown = set(schema) - ANNOTATIONS - KEYWORDS
    if unknown:
        raise SchemaError(f"{where}: unsupported schema keyword(s) {sorted(unknown)}")
    for key, sub in schema.get("properties", {}).items():
        check_schema(sub, f"{where}.{key}")
    if isinstance(schema.get("items"), dict):
        check_schema(schema["items"], f"{where}[]")


def validate(instance, schema: dict, where: str = "$") -> list[str]:
    if where == "$":
        check_schema(schema)
    errors: list[str] = []
    if "type" in schema:
        names = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_is_type(instance, n) for n in names):
            return [f"{where}: expected {'/'.join(names)}, got {type(instance).__name__}"]
    if "const" in schema and instance != schema["const"]:
        errors.append(f"{where}: must be {schema['const']!r}")
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{where}: {instance!r} not in enum {schema['enum']}")
    if isinstance(instance, str):
        if len(instance) < schema.get("minLength", 0):
            errors.append(f"{where}: shorter than {schema['minLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            errors.append(f"{where}: does not match {schema['pattern']}")
    if isinstance(instance, int) and not isinstance(instance, bool) and "minimum" in schema and instance < schema["minimum"]:
        errors.append(f"{where}: below minimum {schema['minimum']}")
    if isinstance(instance, dict):
        for key in schema.get("required", []):
            if key not in instance:
                errors.append(f"{where}: missing required {key!r}")
        props = schema.get("properties", {})
        if schema.get("additionalProperties", True) is False:
            errors += [f"{where}: unexpected property {k!r}" for k in instance if k not in props]
        for key, sub in props.items():
            if key in instance:
                errors += validate(instance[key], sub, f"{where}.{key}")
    if isinstance(instance, list) and "items" in schema:
        for i, item in enumerate(instance):
            errors += validate(item, schema["items"], f"{where}[{i}]")
    return errors


def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text())


def canonical_sha256(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


# ---- reading the sources ---------------------------------------------------------------

def frontmatter(text: str) -> dict[str, str | list[str]]:
    """Top-level `key: value` pairs, with folded (>, |) and `- item` list values."""
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    lines = text[3:end if end > 0 else len(text)].splitlines()
    out: dict[str, str | list[str]] = {}
    i = 0
    while i < len(lines):
        m = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", lines[i])
        i += 1
        if not m:
            continue
        key, value = m.group(1), m.group(2).strip()
        block = []
        # YAML allows an indentless sequence under a key ("allowed-tools:\n- Bash"); missing it
        # read Bash as "no tools" and rated the skill low risk (review P2, 31/10/2026).
        while i < len(lines) and (lines[i].startswith((" ", "\t")) or not lines[i].strip()
                                  or (value == "" and lines[i].startswith("- "))):
            block.append(lines[i].strip())
            i += 1
        if value in (">", "|", ">-", "|-", ">+", "|+", ""):
            items = [b[2:].strip() for b in block if b.startswith("- ")]
            out[key] = items if items and value == "" else " ".join(b for b in block if b)
        else:
            out[key] = value.strip("'\"")
    return out


def as_list(value) -> list[str]:
    if isinstance(value, list):
        return [v.strip("'\" ") for v in value if v.strip()]
    text = str(value or "").strip().strip("[]")
    parts, depth, cur = [], 0, ""
    for ch in text:
        depth += (ch == "(") - (ch == ")")
        if ch in ", " and depth == 0:
            if cur.strip():
                parts.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        parts.append(cur.strip())
    return [p.strip("'\"") for p in parts]


def norm(phrase: str) -> str:
    return " ".join(phrase.lower().strip("'\" ").split())


def router_phrases(index: Path) -> dict[str, list[str]]:
    """Skill name -> the router phrases that route to it (same row pairing as skill_shelf.mjs)."""
    out: dict[str, list[str]] = {}
    try:
        lines = index.read_text().splitlines()
    except OSError:
        return out
    for line in lines:
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.replace("\\|", " ").split("|")]
        if len(cells) < 4:
            continue
        phrases, names = cells[1].split(" · "), cells[2].split(" · ")
        groups = list(zip(phrases, names)) if len(phrases) == len(names) > 1 else [(cells[1], cells[2])]
        for phrase_cell, name_cell in groups:
            found = re.findall(r"`([a-z0-9][a-z0-9:_-]*)`", name_cell)
            if found:
                out.setdefault(found[0], []).extend(norm(p) for p in re.findall(r'"([^"]+)"', phrase_cell))
    return out


def retired_models(path: Path, today: dt.date | None = None) -> set[str]:
    today = today or dt.date.today()
    out = set()
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return out
    for line in lines:
        m = re.match(r"^(\S+)\s+#\s*retired\s+(\d{2})/(\d{2})/(\d{4})", line)
        if m and dt.date(int(m.group(4)), int(m.group(3)), int(m.group(2))) <= today:
            out.add(m.group(1))
    return out


def risk_for(tools: list[str], declared: bool, api_key_lane: bool = False) -> tuple[str, list[str]]:
    reasons: list[str] = []
    level = "low"
    if api_key_lane:
        return "high", ["names an API-key model lane (provider/model)"]
    if not declared:
        return "high", ["no allowed-tools: inherits every tool the session has"]
    for tool in tools:
        if tool in READ_ONLY_TOOLS:
            continue
        if tool in ("*", "Bash", "Bash(*)", "Bash(* *)"):
            return "high", [f"unrestricted {tool}"]
        if tool.startswith("Bash(") or tool in MEDIUM_TOOLS or tool.startswith("mcp__"):
            reasons.append(f"can act through {tool}")
        else:
            reasons.append(f"unrecognised tool {tool}")
        level = "medium"
    return level, reasons


def entry_reviewed(entry: dict, need_vault: bool) -> bool:
    pinned = bool(PIN_RE.match(str(entry.get("pinned_sha") or ""))) or bool(entry.get("npm") and entry.get("pinned_version"))
    return bool(str(entry.get("review") or "").strip()) and pinned and (bool(entry.get("vault")) or not need_vault)


def live_reviewed(roots: Roots, entry_name: str, need_vault: bool) -> bool:
    """The registry as it is NOW: a review withdrawn after generation must not ride on the passport."""
    try:
        registry = json.loads((roots.skills / "skill-watch" / "external-skills.json").read_text()).get("skills", [])
    except (OSError, json.JSONDecodeError):
        return False
    entry = next((e for e in registry if e.get("name") == entry_name), None)
    return bool(entry) and entry_reviewed(entry, need_vault)


def discover(roots: Roots) -> list[tuple[str, Path, Path]]:
    """(origin, root, SKILL.md) for every skill. Symlinked skill dirs are followed (vendored skills
    are links; skipping them left those skills without a passport, review P2 31/10/2026), but the
    origin comes from where the link RESOLVES: a shelf checkout into the vault stays a vault skill
    and keeps the vault's review rules. Each real directory is visited once, so a loop cannot recur."""
    found, seen = [], set()
    vault_real = os.path.realpath(roots.vault)
    for root in (roots.skills, roots.vault):
        if not root.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(root, followlinks=True):
            real = os.path.realpath(dirpath)
            if real in seen:
                dirnames[:] = []
                continue
            seen.add(real)
            dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
            if "SKILL.md" in filenames:
                if real == vault_real or real.startswith(vault_real + os.sep):
                    found.append(("vault", Path(vault_real), Path(vault_real) / os.path.relpath(real, vault_real) / "SKILL.md"))
                else:
                    found.append(("local", root, Path(dirpath) / "SKILL.md"))
    return found


# ---- records -----------------------------------------------------------------------------

def records_path(roots: Roots) -> Path:
    return roots.state / "test-records.jsonl"


def read_records(roots: Roots) -> list[dict]:
    try:
        return [json.loads(line) for line in records_path(roots).read_text().splitlines() if line.strip()]
    except (OSError, json.JSONDecodeError):
        return []


def test_status(records: list[dict], name: str, source_sha: str) -> dict:
    mine = [r for r in records if r.get("skill") == name]
    rejected, stale, latest = [], 0, None
    for r in mine:
        if r.get("recorder") != RECORDER:
            rejected.append(f"record not written by {RECORDER}")
            continue
        if r.get("verdict") != ("PASS" if r.get("exit_code") == 0 else "FAIL"):
            rejected.append(f"verdict {r.get('verdict')} contradicts exit code {r.get('exit_code')}")
            continue
        try:
            log_ok = hashlib.sha256(Path(r["output_path"]).read_bytes()).hexdigest() == r.get("output_sha256")
        except (OSError, KeyError, TypeError):
            log_ok = False
        if not log_ok:
            rejected.append("output log missing or altered since it was recorded")
            continue
        if r.get("source_sha256") != source_sha:
            stale += 1
        else:
            latest = r["verdict"]  # records are appended in time order: the newest run decides
    status = "REJECTED" if rejected else latest if latest else "STALE" if stale else "NONE"
    return {"status": status, "records": len(mine), "rejected": rejected}


def record(roots: Roots, name: str, cmd: list[str], timeout: int = 900) -> dict:
    """Run a test command for a skill and keep its exit code and full output as the record."""
    hit = next((p for o, r, p in discover(roots) if skill_name(p) == name), None)
    if hit is None:
        raise SystemExit(f"no skill named {name} under {roots.skills} or {roots.vault}")
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        rc, output = p.returncode, p.stdout + p.stderr
    except (OSError, subprocess.TimeoutExpired) as e:
        rc, output = 127, str(e)
    at = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    log = roots.state / "records" / f"{name.replace(':', '_')}-{at}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(output)
    rec = {"schema": "test-record/1", "skill": name, "source_sha256": hashlib.sha256(hit.read_bytes()).hexdigest(),
           "command": cmd, "exit_code": rc, "verdict": "PASS" if rc == 0 else "FAIL",
           "output_path": str(log), "output_sha256": hashlib.sha256(log.read_bytes()).hexdigest(),
           "recorded_at": at, "recorder": RECORDER}
    with records_path(roots).open("a") as fh:
        fh.write(json.dumps(rec) + "\n")
    return rec


# ---- generation ---------------------------------------------------------------------------

def skill_name(skill_md: Path) -> str:
    try:
        name = frontmatter(skill_md.read_text(errors="replace")).get("name")
    except OSError:
        name = None
    return str(name or skill_md.parent.name)


def generate(roots: Roots) -> dict:
    try:
        registry = json.loads((roots.skills / "skill-watch" / "external-skills.json").read_text()).get("skills", [])
    except (OSError, json.JSONDecodeError):
        registry = []
    try:
        homes = json.loads((roots.skills / "HOMES.json").read_text()).get("homes", {})
    except (OSError, json.JSONDecodeError):
        homes = {}
    by_entry = {e.get("name"): e for e in registry}
    phrases = router_phrases(roots.skills / "index.md")
    records = read_records(roots)
    passports, seen, shadowed = [], set(), []
    for origin, root, skill_md in discover(roots):
        raw = skill_md.read_bytes()
        fm = frontmatter(raw.decode(errors="replace"))
        name = str(fm.get("name") or skill_md.parent.name)
        if name in seen:
            shadowed.append({"name": name, "path": str(skill_md)})  # first one wins, as in skill_shelf
            continue
        seen.add(name)
        rel = skill_md.relative_to(root)
        source_sha = hashlib.sha256(raw).hexdigest()
        description = str(fm.get("description") or "")
        tools = as_list(fm.get("allowed-tools"))
        model = str(fm["model"]) if fm.get("model") else None
        api_lane = bool(model and "/" in model)
        level, reasons = risk_for(tools, "allowed-tools" in fm, api_lane)
        if origin == "vault":
            entry = by_entry.get(rel.parts[0])
            reviewed = bool(entry) and entry_reviewed(entry, need_vault=True)
        else:
            entry = by_entry.get(skill_md.parent.name)
            reviewed = entry_reviewed(entry, need_vault=False) if entry else True
        caps = sorted({norm(c) for c in as_list_caps(fm.get("capabilities"))} | set(phrases.get(name, [])))
        passports.append({
            "schema": "capability-passport/1", "name": name, "origin": origin,
            "source": {"path": str(rel), "sha256": source_sha},
            "identity": {"description": description, "description_sha256": hashlib.sha256(description.encode()).hexdigest()},
            "owner": str(fm.get("owner") or fm.get("owner_role") or homes.get(name) or "unknown"),
            "capabilities": caps,
            "tools": {"declared": "allowed-tools" in fm, "list": tools},
            "model": model, "api_key_lane": api_lane,
            "risk": {"level": level, "reasons": reasons},
            "trust": {"reviewed": reviewed,
                      "review": (str(entry.get("review") or "") or None) if entry else
                                (None if origin == "vault" else "local skill: lands through the library's PR release gate"),
                      "pinned_sha": (entry.get("pinned_sha") or entry.get("pinned_version")) if entry else None,
                      "registry": entry.get("name") if entry else None},
            "tests": test_status(records, name, source_sha),
            "conflicts": [],
        })
    claims: dict[str, set[str]] = {}
    for p in passports:
        for cap in p["capabilities"]:
            claims.setdefault(cap, set()).add(p["owner"])
    conflicts = []
    for cap, owners in sorted(claims.items()):
        if len(owners) > 1:
            conflicts.append({"capability": cap, "owners": sorted(owners)})
    by_cap = {c["capability"]: c for c in conflicts}
    for p in passports:
        p["conflicts"] = [by_cap[c] for c in p["capabilities"] if c in by_cap]
    return {"schema": "capability-passports/1", "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "skills_root": str(roots.skills), "vault_root": str(roots.vault), "count": len(passports),
            "conflicts": conflicts, "shadowed": shadowed, "passports": passports}


def as_list_caps(value) -> list[str]:
    """Capabilities are phrases, so only commas separate them (as_list also splits on spaces)."""
    if isinstance(value, list):
        return value
    return [c for c in str(value or "").strip().strip("[]").split(",") if c.strip()]


# ---- activation (simulated) -----------------------------------------------------------------

def activate(roots: Roots, doc: dict, name: str, capability: str | None = None, max_risk: str = "medium",
             model: str | None = None, available_models: list[str] | None = None, require_tested: bool = False) -> dict:
    codes: list[str] = []
    details: list[str] = []

    def refuse(code: str, detail: str) -> None:
        if code not in codes:
            codes.append(code)
        details.append(f"{code}: {detail}")

    receipt = {"schema": "activation-receipt/1", "simulated": True, "installed": False,
               "at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "skill": name,
               "request": {"capability": capability, "max_risk": max_risk, "require_tested": require_tested}}
    p = next((x for x in doc.get("passports", []) if x.get("name") == name), None)
    if p is None:
        refuse("NO_PASSPORT", f"no passport for {name}; run generate first")
        return {**receipt, "decision": "REFUSE", "codes": codes, "details": details,
                "passport_sha256": None, "model": {"needed": model, "available": available_models, "substitute": None}}
    errors = validate(p, load_schema())
    if errors:
        # Stop here: the checks below read fields the schema just said may be missing, and a
        # KeyError instead of a receipt was the review P2 of 31/10/2026.
        refuse("SCHEMA_INVALID", "; ".join(errors[:5]))
        return {**receipt, "decision": "REFUSE", "codes": codes, "details": details,
                "passport_sha256": canonical_sha256(p), "model": {"needed": model, "available": available_models, "substitute": None}}
    root = roots.vault if p.get("origin") == "vault" else roots.skills
    try:
        current = hashlib.sha256((root / p["source"]["path"]).read_bytes()).hexdigest()
    except (OSError, KeyError, TypeError):
        current = None
    if current != p["source"]["sha256"]:
        refuse("STALE_SHA", f"SKILL.md is {current or 'missing'}, passport pins {p['source']['sha256']}")
    if not p["trust"]["reviewed"]:
        refuse("UNREVIEWED", "outside skill without a review and a 40-char pinned SHA in external-skills.json")
    elif p["trust"]["registry"] and not live_reviewed(roots, p["trust"]["registry"], p["origin"] == "vault"):
        refuse("UNREVIEWED", f"registry entry {p['trust']['registry']} lost its review or pin after the passport was generated")
    if p["tests"]["status"] == "REJECTED":
        refuse("FAKE_PASS", "; ".join(p["tests"]["rejected"]))
    if require_tested and p["tests"]["status"] != "PASS":
        refuse("UNTESTED", f"test status is {p['tests']['status']}, not a PASS bound to this SKILL.md")
    if capability:
        cap = norm(capability)
        if cap not in p["capabilities"]:
            refuse("MISSING_CAPABILITY", f"{name} does not declare {cap!r}")
        clash = next((c for c in p["conflicts"] if c["capability"] == cap), None)
        if clash:
            refuse("CONFLICTING_OWNERS", f"{cap!r} is claimed by owners {clash['owners']}")
    if RISK_ORDER.get(p["risk"]["level"], 2) > RISK_ORDER.get(max_risk, 0):
        refuse("RISK_ABOVE_LIMIT", f"risk {p['risk']['level']} over limit {max_risk}: {'; '.join(p['risk']['reasons'])}")
    needed = model or p["model"]
    if p["api_key_lane"] or (needed and "/" in needed):
        refuse("API_KEY_LANE", f"{needed} is an API-key lane; subscription accounts only")
    if needed:
        if needed in retired_models(roots.retired):
            refuse("MODEL_RETIRED", f"{needed} is in retired-models.txt")
        elif available_models is None:
            refuse("MODEL_UNKNOWN", f"{name} needs {needed} and no available-model list was given")
        elif needed not in available_models:
            refuse("MODEL_UNAVAILABLE", f"{needed} is not among {available_models}; no substitute is chosen")
    return {**receipt, "decision": "REFUSE" if codes else "ALLOW", "codes": codes, "details": details,
            "passport_sha256": canonical_sha256(p),
            "source_sha256": {"passport": p["source"]["sha256"], "current": current},
            "model": {"needed": needed, "available": available_models, "substitute": None}}


# ---- CLI ------------------------------------------------------------------------------------

def _opt(args: list[str], flag: str, default=None):
    return args[args.index(flag) + 1] if flag in args and args.index(flag) + 1 < len(args) else default


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in ("generate", "activate", "record", "validate"):
        print(__doc__)
        return 2
    cmd, args = argv[0], argv[1:]
    roots = Roots.default(skills=Path(_opt(args, "--skills-root")) if _opt(args, "--skills-root") else None,
                          vault=Path(_opt(args, "--vault-root")) if _opt(args, "--vault-root") else None,
                          state=Path(_opt(args, "--state")) if _opt(args, "--state") else None)
    store = Path(_opt(args, "--out") or _opt(args, "--passports") or roots.state / "passports.json")
    if cmd == "record":
        if "--" not in args or len(args) < 3:
            print("usage: record <name> -- <test command ...>", file=sys.stderr)
            return 2
        roots.state.mkdir(parents=True, exist_ok=True)
        rec = record(roots, args[0], args[args.index("--") + 1:])
        print(json.dumps(rec, indent=2))
        return 0 if rec["verdict"] == "PASS" else 1
    if cmd == "generate":
        doc = generate(roots)
        store.parent.mkdir(parents=True, exist_ok=True)
        store.write_text(json.dumps(doc, indent=2) + "\n")
        print(f"{doc['count']} passports, {len(doc['conflicts'])} capability conflicts, "
              f"{len(doc['shadowed'])} shadowed names -> {store}")
        if "--validate" not in args:
            return 0
    try:
        doc = json.loads(store.read_text())
    except (OSError, json.JSONDecodeError) as e:
        if cmd != "activate":
            print(f"cannot read passports at {store}: {e}", file=sys.stderr)
            return 1
        doc = generate(roots)  # first use on this machine: build them now, the receipt still checks every rule
    if cmd in ("generate", "validate"):
        schema = load_schema()
        bad = {p.get("name"): validate(p, schema) for p in doc.get("passports", [])}
        bad = {k: v for k, v in bad.items() if v}
        for name, errs in bad.items():
            print(f"INVALID {name}: {'; '.join(errs[:3])}")
        print(f"{len(doc.get('passports', [])) - len(bad)}/{len(doc.get('passports', []))} passports valid")
        return 1 if bad or not doc.get("passports") else 0
    if not args or args[0].startswith("--"):
        print("usage: activate <name> [--capability C] [--max-risk L] [--model M] [--available-models a,b]", file=sys.stderr)
        return 2
    max_risk = _opt(args, "--max-risk", "medium")
    if max_risk not in RISK_ORDER:
        print(f"--max-risk must be one of {list(RISK_ORDER)}", file=sys.stderr)
        return 2
    avail = _opt(args, "--available-models")
    receipt = activate(roots, doc, args[0], capability=_opt(args, "--capability"), max_risk=max_risk,
                       model=_opt(args, "--model"), require_tested="--require-tested" in args,
                       available_models=[m.strip() for m in avail.split(",") if m.strip()] if avail is not None else None)
    roots.state.mkdir(parents=True, exist_ok=True)
    with (roots.state / "activation-receipts.jsonl").open("a") as fh:
        fh.write(json.dumps(receipt) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0 if receipt["decision"] == "ALLOW" else 3


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
