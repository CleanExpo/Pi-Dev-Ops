"""Library skills name their own files as ~/.claude/skills/<name>/...; the image links every shipped
skill there (scripts/link_skills_home.sh, run by the Dockerfile), so those paths resolve.
Review round 2 P1-LIBRARY-SKILL-ABSOLUTE-PATHS."""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COPY = ROOT / "skills-library" / "skills"
REF = re.compile(r"(?:~|\$HOME|\$\{HOME\})/\.claude/skills/([A-Za-z0-9._-]+)(/[A-Za-z0-9._/{}<>*-]*)?")


def _link(tmp_path):
    home = tmp_path / "skills"
    subprocess.run(["sh", str(ROOT / "scripts" / "link_skills_home.sh"), str(home), str(ROOT)], check=True)
    return home


def _needs_to_exist(name: str, rest: str, source: Path) -> bool:
    """Placeholders (<domain>), files a skill writes at run time (seo/output/, .env) and paths quoted
    inside a skill's test fixtures are not files the image must carry."""
    return not (re.search(r"[<>{}*]", rest) or rest.endswith("/.env") or "/output/" in rest
                or "tests" in source.relative_to(COPY).parts)


def test_every_path_a_library_skill_names_resolves_in_the_image(tmp_path):
    """Checked for the copies that load: a library skill that also has a skills/ copy is shadowed
    by it (the loader and the links both prefer skills/), so its library text is never read."""
    home = _link(tmp_path)
    shadowed = {p.name for p in (ROOT / "skills").iterdir()}
    checked, missing = 0, []
    for source in COPY.rglob("*"):
        if not source.is_file() or source.relative_to(COPY).parts[0] in shadowed:
            continue
        try:
            text = source.read_text("utf-8")
        except UnicodeDecodeError:
            continue
        for m in REF.finditer(text):
            name, rest = m.group(1), (m.group(2) or "").rstrip(".")
            if not _needs_to_exist(name, rest, source):
                continue
            checked += 1
            if not (home / name / rest.lstrip("/")).exists():
                missing.append(f"{source.relative_to(COPY)} -> {name}{rest}")
    assert checked > 100 and missing == []


def test_a_skill_in_both_places_links_to_this_repos_copy(tmp_path):
    home = _link(tmp_path)
    both = sorted({p.name for p in COPY.iterdir()} & {p.name for p in (ROOT / "skills").iterdir()})
    assert both, "no overlap to check"
    for name in both:
        assert (home / name).resolve() == (ROOT / "skills" / name).resolve()
    assert (home / "ceo-board").resolve() == (COPY / "ceo-board").resolve()


def test_the_script_refuses_a_symlinked_source_or_a_real_entry_in_the_way(tmp_path):
    """Review round 5 P1-LINK-SKILL-SYMLINK-ESCAPES-REPO: skills/bad -> outside/ was linked into
    the skills home, so the image exposed a directory outside both skill roots."""
    root, outside = tmp_path / "root", tmp_path / "outside"
    (root / "skills-library" / "skills" / "good").mkdir(parents=True)
    (root / "skills").mkdir()
    outside.mkdir()
    (root / "skills" / "bad").symlink_to(outside, target_is_directory=True)
    script = str(ROOT / "scripts" / "link_skills_home.sh")
    run = subprocess.run(["sh", script, str(tmp_path / "home"), str(root)], capture_output=True, text=True)
    assert run.returncode != 0 and "symlink" in run.stderr and not (tmp_path / "home" / "bad").exists()
    (root / "skills" / "bad").unlink()
    (tmp_path / "home2" / "good").mkdir(parents=True)
    run = subprocess.run(["sh", script, str(tmp_path / "home2"), str(root)], capture_output=True, text=True)
    assert run.returncode != 0 and "already there" in run.stderr
    assert not (tmp_path / "home2" / "good" / "good").exists()


def test_the_image_runs_the_link_script_after_copying_both_trees():
    lines = (ROOT / "Dockerfile").read_text().splitlines()
    run = next(i for i, ln in enumerate(lines) if "scripts/link_skills_home.sh /home/pidev/.claude/skills" in ln)
    for copied in ("COPY skills/ ", "COPY skills-library/ ", "COPY scripts/ "):
        assert any(ln.startswith(copied) for ln in lines[:run])
