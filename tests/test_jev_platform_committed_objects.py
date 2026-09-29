"""Round 12 P1s: every reader of reviewed content goes through jev_platform/committed.py, which rehashes the commit,
every tree on the path and the blob, with refs/replace ignored.

P1-MANIFEST-UNCOMMITTED-DISCLOSURE (ask.py), P1-LIVE-FIXTURE-UNCHECKED-BLOB (__main__.py),
P1-WRITER-CONTROL-UNCOMMITTED-APPROVAL (generate.py) and P1-COMMITTED-TREE-INTEGRITY-BYPASS (engine.py), reproduced
the way the reviewer did: replace or overwrite an object under its original id, HEAD unchanged. Offline, temp repos.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import zlib

import pytest
import test_jev_platform_committed_inputs as ci
from jev_scale_support import git
from test_jev_platform_committed_inputs import MARKER, RULE, budget, recording

from evals.jev_constitution import generate, harness, quotes
from jev_platform import __main__ as cli
from jev_platform import ask, committed, engine

repo, eval_repo = ci.repo, ci.eval_repo  # temp repos standing in for engine.ROOT and the eval harness


def out(root, *args, stdin=None) -> str:
    return subprocess.run(["git", "-C", str(root), *args], input=stdin, capture_output=True, text=True).stdout.strip()


def new_repo(root, files: dict) -> str:
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    git(root, "init", "-q")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "reviewed")
    return out(root, "rev-parse", "HEAD")


def overwrite(root, oid: str, kind: bytes, data: bytes) -> None:
    """Store `data` under `oid`, as a corrupted or hand-written loose object would."""
    path = root / ".git" / "objects" / oid[:2] / oid[2:]
    path.chmod(0o644)
    path.write_bytes(zlib.compress(kind + b" %d\0" % len(data) + data))


def raw(root, oid: str) -> bytes:
    """The object's content bytes (`cat-file <type> <id>`), ready to store under another id."""
    kind = out(root, "cat-file", "-t", oid)
    return subprocess.run(["git", "-C", str(root), "cat-file", kind, oid], capture_output=True).stdout


def unreviewed_commit(root, rel: str, text: str) -> str:
    """A second commit holding `text` at `rel`, then HEAD reset back so the tree above is still the reviewed one."""
    reviewed = out(root, "rev-parse", "HEAD")
    (root / rel).write_text(text)
    git(root, "commit", "-qam", "unreviewed")
    other = out(root, "rev-parse", "HEAD")
    git(root, "reset", "-q", "--hard", reviewed)
    return other


# ---- committed.py itself

def test_an_honest_file_reads_back_with_its_blob_id(tmp_path):
    commit = new_repo(tmp_path, {"d/f.txt": "reviewed\n"})
    assert committed.read(tmp_path, "d/f.txt", commit) == (out(tmp_path, "rev-parse", "HEAD:d/f.txt"), b"reviewed\n",
                                                           b"100644")


@pytest.mark.parametrize("level", ["blob", "tree", "root", "commit"])
def test_an_object_whose_bytes_do_not_hash_to_its_id_is_refused(tmp_path, level):
    commit = new_repo(tmp_path, {"d/f.txt": "reviewed\n"})
    other = unreviewed_commit(tmp_path, "d/f.txt", f"{MARKER}\n")
    pairs = {"blob": ("HEAD:d/f.txt", f"{other}:d/f.txt"), "tree": ("HEAD:d", f"{other}:d"),
             "root": ("HEAD^{tree}", f"{other}^{{tree}}"), "commit": ("HEAD", other)}
    reviewed_oid, swap_oid = (out(tmp_path, "rev-parse", r) for r in pairs[level])
    kind = out(tmp_path, "cat-file", "-t", reviewed_oid).encode()
    overwrite(tmp_path, reviewed_oid, kind, raw(tmp_path, swap_oid))
    assert MARKER in out(tmp_path, "show", "HEAD:d/f.txt")  # positive control: git itself now serves the swap
    assert committed.read(tmp_path, "d/f.txt", commit) is None


def test_a_replaced_object_is_not_followed(tmp_path):
    commit = new_repo(tmp_path, {"f.txt": "reviewed\n"})
    other = unreviewed_commit(tmp_path, "f.txt", f"{MARKER}\n")
    git(tmp_path, "replace", commit, other)
    assert MARKER in out(tmp_path, "show", "HEAD:f.txt")
    assert committed.read(tmp_path, "f.txt", committed.resolve(tmp_path))[1] == b"reviewed\n"


def test_a_name_instead_of_an_object_id_is_refused(tmp_path):
    new_repo(tmp_path, {"f.txt": "reviewed\n"})
    assert committed.read(tmp_path, "f.txt", "HEAD") is None and committed.blob(tmp_path, "HEAD:f.txt") is None


def test_an_id_carrying_a_newline_cannot_desynchronise_later_reads(tmp_path):
    new_repo(tmp_path, {"a.txt": "first\n", "b.txt": "second\n"})
    a, b = out(tmp_path, "rev-parse", "HEAD:a.txt"), out(tmp_path, "rev-parse", "HEAD:b.txt")
    with committed.Objects(tmp_path) as objects:
        assert objects.get(f"{a}\n{b}", b"blob") is None
        assert objects.get(a, b"blob") == b"first\n"  # not b's reply left behind in the pipe


def test_an_object_of_another_type_is_refused(tmp_path):
    commit = new_repo(tmp_path, {"f.txt": "reviewed\n"})
    with committed.Objects(tmp_path) as objects:
        assert objects.get(out(tmp_path, "rev-parse", "HEAD:f.txt"), b"tree") is None
        assert objects.get(commit, b"blob") is None
    assert committed.read(tmp_path, "f.txt/inner", commit) is None  # a blob is never walked as a tree


def test_ancestry_is_walked_through_verified_commits_only(tmp_path):
    first = new_repo(tmp_path, {"f.txt": "one\n"})
    (tmp_path / "f.txt").write_text("two\n")
    git(tmp_path, "commit", "-qam", "two")
    head = out(tmp_path, "rev-parse", "HEAD")
    assert committed.is_ancestor(tmp_path, first, head)  # positive control
    body = raw(tmp_path, head)
    overwrite(tmp_path, head, b"commit", body.replace(b"two", b"TWO"))
    assert not committed.is_ancestor(tmp_path, first, head)


# ---- the four readers the reviewer named

def test_the_approval_manifest_is_read_through_verified_objects(tmp_path):
    none_approved = json.dumps({"files": {}, "questions": {}})
    new_repo(tmp_path, {ask.MANIFEST: none_approved, "internal.txt": MARKER})
    approving = json.dumps({"files": {"internal.txt": "x"}, "questions": {}})
    swap = out(tmp_path, "hash-object", "-w", "--stdin", stdin=approving)
    git(tmp_path, "replace", out(tmp_path, "rev-parse", f"HEAD:{ask.MANIFEST}"), swap)
    assert ask.approved_manifest(str(tmp_path)) == {"files": {}, "questions": {}}
    git(tmp_path, "replace", "-d", out(tmp_path, "rev-parse", f"HEAD:{ask.MANIFEST}"))
    overwrite(tmp_path, out(tmp_path, "rev-parse", f"HEAD:{ask.MANIFEST}"), b"blob", approving.encode())
    assert "internal.txt" in out(tmp_path, "show", f"HEAD:{ask.MANIFEST}")
    assert ask.approved_manifest(str(tmp_path)) is None


def test_the_live_fixture_is_read_through_verified_objects(repo):
    fixture = repo / cli.FIXTURE_AT_HEAD
    fixture.parent.mkdir(parents=True)
    fixture.write_text(json.dumps({"actions": {"safe": "The agent reports tests have not run yet."}}))
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "fixture")
    assert cli._committed_actions() == {"safe": "The agent reports tests have not run yet."}  # positive control
    overwrite(repo, out(repo, "rev-parse", f"HEAD:{cli.FIXTURE_AT_HEAD}"), b"blob",
              json.dumps({"actions": {"safe": MARKER}}).encode())
    assert cli._committed_actions() == {}


@pytest.mark.parametrize("how", ["replace", "overwrite"])
def test_the_writer_control_is_read_through_verified_objects(tmp_path, monkeypatch, capsys, how):
    new_repo(tmp_path, {"control.json": json.dumps({"status": "run", "verdict": "do-not-use"})})
    monkeypatch.setattr(generate, "WRITER_CONTROL", tmp_path / "control.json")
    use = json.dumps({"status": "run", "verdict": "use"})
    reviewed = out(tmp_path, "rev-parse", "HEAD:control.json")
    if how == "replace":
        git(tmp_path, "replace", reviewed, out(tmp_path, "hash-object", "-w", "--stdin", stdin=use))
    else:
        overwrite(tmp_path, reviewed, b"blob", use.encode())
    assert '"use"' in out(tmp_path, "show", "HEAD:control.json")
    args = argparse.Namespace(writer="gemini", question=RULE, max_usd=1.0)
    assert generate._writer(args) is None
    assert "writer control" in capsys.readouterr().err


def test_a_working_copy_symlink_cannot_pick_another_committed_control(tmp_path, monkeypatch, capsys):
    """Round 13 P1-COMMITTED-PATH-WORKTREE-SYMLINK, the reviewer's reproduction."""
    new_repo(tmp_path, {"control.json": json.dumps({"status": "run", "verdict": "do-not-use"}),
                        "other.json": json.dumps({"status": "run", "verdict": "use"})})
    control = tmp_path / "control.json"
    monkeypatch.setattr(generate, "WRITER_CONTROL", control)
    assert committed.file_at_head(control) is not None  # positive control: the committed control reads back
    control.unlink()
    control.symlink_to("other.json")
    assert committed.file_at_head(control) is None
    args = argparse.Namespace(writer="gemini", question=RULE, max_usd=1.0)
    assert generate._writer(args) is None and "writer control" in capsys.readouterr().err


def test_a_symlinked_directory_on_the_path_is_refused(tmp_path):
    new_repo(tmp_path, {"real/q.json": "reviewed", "other/q.json": MARKER})
    assert committed.file_at_head(tmp_path / "real" / "q.json") == b"reviewed"
    (tmp_path / "real" / "q.json").unlink()
    (tmp_path / "real").rmdir()
    (tmp_path / "real").symlink_to("other")
    assert committed.file_at_head(tmp_path / "real" / "q.json") is None


def test_the_eval_harness_refuses_a_symlinked_registry(eval_repo):
    (eval_repo / "alt.json").write_text(json.dumps({"questions": [{"id": "alt", "question": MARKER}]}))
    git(eval_repo, "add", "alt.json")
    git(eval_repo, "commit", "-qm", "alt")
    assert harness.committed_questions() != []  # positive control
    (eval_repo / "questions.json").unlink()
    (eval_repo / "questions.json").symlink_to("alt.json")
    assert harness.committed_questions() == []


def test_a_rewritten_root_tree_sends_nothing(repo):
    reviewed_tree = out(repo, "rev-parse", "HEAD^{tree}")
    questions = json.loads((repo / "evals/jev_constitution/questions.json").read_text())
    for q in questions["questions"]:
        q.update(question=MARKER, criteria_true=MARKER, criteria_false=MARKER)
    other = unreviewed_commit(repo, "evals/jev_constitution/questions.json", json.dumps(questions))
    overwrite(repo, reviewed_tree, b"tree", raw(repo, out(repo, "rev-parse", f"{other}^{{tree}}")))
    assert MARKER in out(repo, "show", "HEAD:evals/jev_constitution/questions.json")
    sent = []
    engine.decide("The agent writes 'all tests passed' but no test ran.", [RULE], 1, recording(sent), budget(0.5))
    assert sent == []


def test_quotes_refuse_a_tampered_constitution(tmp_path):
    new_repo(tmp_path, {"CONSTITUTION.md": "Reviewed text.\n"})
    assert quotes.read_source(str(tmp_path), "HEAD", "CONSTITUTION.md") == "Reviewed text.\n"
    overwrite(tmp_path, out(tmp_path, "rev-parse", "HEAD:CONSTITUTION.md"), b"blob", f"{MARKER}\n".encode())
    with pytest.raises(ValueError):
        quotes.read_source(str(tmp_path), "HEAD", "CONSTITUTION.md")
