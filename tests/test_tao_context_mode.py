"""tests/test_tao_context_mode.py — RA-1969 summary-index unit tests.

Pure in-process tests using tmp_path fixtures. No SDK, no network.
Cover: build_index walk, symbol extraction (Python + TS), determinism,
ignore globs, sha256 drift, kill-switch abort, empty repo, large-file
synopsis truncation, expand hit accounting.
"""
from __future__ import annotations

from pathlib import Path

from app.server.tao_context_mode import (
    build_index,
    expand,
    stats,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _seed_repo(root: Path) -> None:
    """Lay down a small mixed Python + TS repo under root."""
    (root / "app").mkdir(parents=True, exist_ok=True)
    (root / "web").mkdir(parents=True, exist_ok=True)
    (root / "app" / "core.py").write_text(
        '"""Core utilities for the app."""\n'
        "import os\n\n"
        "class Engine:\n"
        "    def start(self):\n"
        "        def helper():\n"
        "            return 1\n"
        "        return helper()\n\n"
        "async def shutdown():\n"
        "    return None\n",
        encoding="utf-8",
    )
    (root / "web" / "index.ts").write_text(
        "// entry point of the web app\n"
        "export const VERSION = '1.0.0';\n"
        "export function bootstrap() { return true; }\n"
        "class Renderer { draw() {} }\n",
        encoding="utf-8",
    )


# ── Walk + symbol extraction ──────────────────────────────────────────────────

def test_build_index_walks_and_extracts_python_symbols(tmp_path):
    _seed_repo(tmp_path)
    idx = build_index(tmp_path)
    py = idx.summaries["app/core.py"]
    # Top-level only (^def / ^class) — indented helpers + methods excluded.
    assert py.symbols == ["Engine", "shutdown"]
    assert "Core utilities" in py.summary
    assert py.size_bytes > 0
    assert py.line_count >= 6


def test_build_index_extracts_typescript_symbols(tmp_path):
    _seed_repo(tmp_path)
    idx = build_index(tmp_path)
    ts = idx.summaries["web/index.ts"]
    assert "bootstrap" in ts.symbols
    assert "Renderer" in ts.symbols
    assert "VERSION" in ts.symbols
    assert "entry point" in ts.summary


def test_build_index_total_bytes_and_file_count(tmp_path):
    _seed_repo(tmp_path)
    idx = build_index(tmp_path)
    assert len(idx.summaries) == 2
    assert idx.total_bytes_indexed > 0
    assert idx.bypassed is False


# ── expand + stats ────────────────────────────────────────────────────────────

def test_expand_returns_full_content_and_records_hit(tmp_path):
    _seed_repo(tmp_path)
    idx = build_index(tmp_path)
    content = expand(idx, "app/core.py")
    assert "class Engine" in content
    s = stats(idx)
    assert s["expansions"] == 1
    assert s["expanded_bytes"] > 0


def test_expand_max_lines_truncates(tmp_path):
    _seed_repo(tmp_path)
    idx = build_index(tmp_path)
    content = expand(idx, "app/core.py", max_lines=2)
    assert content.count("\n") <= 3
    assert "truncated" in content


# ── Determinism ───────────────────────────────────────────────────────────────

def test_build_index_is_deterministic(tmp_path):
    _seed_repo(tmp_path)
    a = build_index(tmp_path)
    b = build_index(tmp_path)
    assert set(a.summaries.keys()) == set(b.summaries.keys())
    for path, sa in a.summaries.items():
        sb = b.summaries[path]
        assert sa.sha256_hex == sb.sha256_hex
        assert sa.symbols == sb.symbols
        assert sa.summary == sb.summary
        assert sa.size_bytes == sb.size_bytes


# ── Ignore globs ──────────────────────────────────────────────────────────────

def test_default_ignore_globs_skip_node_modules_and_git(tmp_path):
    _seed_repo(tmp_path)
    nm = tmp_path / "node_modules" / "lib"
    nm.mkdir(parents=True)
    (nm / "leaf.js").write_text("export const x = 1;\n", encoding="utf-8")
    git = tmp_path / ".git"
    git.mkdir()
    (git / "HEAD.py").write_text("# secret\n", encoding="utf-8")
    idx = build_index(tmp_path)
    assert "node_modules/lib/leaf.js" not in idx.summaries
    assert ".git/HEAD.py" not in idx.summaries


def test_custom_ignore_globs_override_default(tmp_path):
    _seed_repo(tmp_path)
    idx = build_index(tmp_path, ignore_globs=["app", "app/*"])
    assert "app/core.py" not in idx.summaries
    assert "web/index.ts" in idx.summaries


# ── sha256 drift ──────────────────────────────────────────────────────────────

def test_expand_warns_on_sha256_drift(tmp_path, caplog):
    _seed_repo(tmp_path)
    idx = build_index(tmp_path)
    target = tmp_path / "app" / "core.py"
    target.write_text(target.read_text(encoding="utf-8") + "\n# drift\n", encoding="utf-8")
    with caplog.at_level("WARNING", logger="pi-ceo.tao_context_mode"):
        content = expand(idx, "app/core.py")
    assert "drift" in content
    assert any("sha256 drift" in rec.message for rec in caplog.records)


# ── Kill-switch abort ─────────────────────────────────────────────────────────

def test_build_index_respects_kill_switch_hard_stop(tmp_path, monkeypatch):
    _seed_repo(tmp_path)
    flag = tmp_path / "HARD_STOP"
    flag.write_text("stop", encoding="utf-8")
    monkeypatch.setenv("TAO_HARD_STOP_FILE", str(flag))
    idx = build_index(tmp_path)
    assert idx.bypassed is True
    assert idx.bypass_reason == "kill_switch:HARD_STOP"


# ── Empty repo ────────────────────────────────────────────────────────────────

def test_build_index_empty_repo(tmp_path):
    idx = build_index(tmp_path)
    assert idx.summaries == {}
    assert idx.total_bytes_indexed == 0
    assert idx.bypassed is False


# ── Large-file synopsis ───────────────────────────────────────────────────────

def test_synopsis_stays_short_for_large_file(tmp_path):
    big = tmp_path / "big.py"
    body = (
        '"""A big file with many lines but a short docstring."""\n'
        + "x = 1\n" * 5000
    )
    big.write_text(body, encoding="utf-8")
    idx = build_index(tmp_path)
    summary = idx.summaries["big.py"]
    assert len(summary.summary) <= 250
    assert summary.size_bytes > 10_000
    assert "big file" in summary.summary
