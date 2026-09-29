"""Build the labelled skill-routing corpus: request text -> the one skill it needs, or none.

Requests are written by Claude (subscription CLI, `claude -p`) from each skill's name and
description only; the generator never sees the router or its scoring. Negatives are
requests no skill fits. Split is by skill (hash), so held-out skills are never tuned on.

usage: python -m evals.skill_routing.generate_corpus --library <skills-library checkout> \
           --out evals/skill_routing/corpus.jsonl [--per-skill 8] [--negatives 400]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from src.tao import skills as tao_skills

BATCH = 15
MODEL = "claude-sonnet-5"
ASK = (
    "Below are skills (name: what it does). For EACH skill write {n} different requests a busy, "
    "non-technical founder might type into a command box that need exactly that skill. Vary length "
    "and tone; some terse, some rambling. Do not use the skill's name, and prefer everyday words "
    "over the description's own distinctive terms. Reply with JSON only: "
    '{{"<skill name>": ["request", ...], ...}}\n\n{skills}'
)
ASK_NONE = (
    "Write {n} different short requests a founder might type into a work command box that need NO "
    "specialist skill: small talk, personal errands, general trivia, weather, jokes, things outside "
    "software, marketing, finance or operations. Reply with JSON only: a list of strings."
)


def catalogue(library: Path) -> dict[str, dict]:
    """Pi-Dev-Ops skills plus library skills that live nowhere else (one home per skill)."""
    items = {n: {"name": n, "description": str(s["description"]), "home": "pi-dev-ops"}
             for n, s in tao_skills.load_all_skills().items()}
    for path in sorted((library / "skills").glob("*/SKILL.md")):
        if path.parent.is_symlink() or path.parent.name in items:
            continue
        meta, _ = tao_skills._parse_frontmatter(path.read_text(encoding="utf-8"))
        name = str(meta.get("name", path.parent.name))
        if name not in items and meta.get("description"):
            items[name] = {"name": name, "description": str(meta["description"]), "home": "library"}
    return items


def ask_claude(prompt: str, cache: Path) -> object | None:
    """One batch, retried; each good answer is saved so a rerun resumes. None after 3 misses."""
    hit = cache / (hashlib.sha256(prompt.encode()).hexdigest()[:16] + ".json")
    if hit.exists():
        return json.loads(hit.read_text("utf-8"))
    for _ in range(3):
        out = subprocess.run(["claude", "-p", "--model", MODEL, prompt], capture_output=True, text=True,
                             stdin=subprocess.DEVNULL, timeout=600).stdout
        starts = [i for i in (out.find("{"), out.find("[")) if i >= 0]
        try:
            answer = json.loads(out[min(starts): max(out.rfind("}"), out.rfind("]")) + 1])
        except (ValueError, json.JSONDecodeError):
            continue
        hit.write_text(json.dumps(answer, ensure_ascii=False), "utf-8")
        return answer
    return None


def split_for(name: str) -> str:
    return "heldout" if int(hashlib.sha256(name.encode()).hexdigest(), 16) % 10 < 3 else "tune"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--library", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--per-skill", type=int, default=8)
    ap.add_argument("--negatives", type=int, default=400)
    args = ap.parse_args()
    items = catalogue(args.library)
    names = sorted(items)
    batches = [names[i:i + BATCH] for i in range(0, len(names), BATCH)]
    prompts = [ASK.format(n=args.per_skill, skills="\n".join(f"- {n}: {items[n]['description'][:400]}" for n in b))
               for b in batches]
    prompts += [ASK_NONE.format(n=100) + f"\n(set {i + 1})" for i in range(max(args.negatives // 100, 0))]
    cache = Path(tempfile.gettempdir()) / "skill_routing_corpus_cache"
    cache.mkdir(exist_ok=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        answers = list(pool.map(lambda p: ask_claude(p, cache), prompts))
    missed = sum(a is None for a in answers)
    if missed:
        print(f"{missed} of {len(prompts)} batches gave no usable answer after 3 tries; rerun to resume")
        return 1
    rows = []
    for answer in answers:
        if isinstance(answer, dict):
            rows += [{"text": t, "expected": n, "home": items[n]["home"], "kind": "paraphrase",
                      "split": split_for(n)} for n, ts in answer.items() if n in items for t in ts]
        else:
            rows += [{"text": t, "expected": None, "kind": "negative", "split": "tune" if i % 10 < 7 else "heldout"}
                     for i, t in enumerate(answer)]
    with args.out.open("w", encoding="utf-8") as fh:
        for i, row in enumerate(rows):
            fh.write(json.dumps({"id": i, **row}, ensure_ascii=False) + "\n")
    print(f"{len(rows)} cases, {len(items)} skills, {sum(r['expected'] is None for r in rows)} negatives -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
