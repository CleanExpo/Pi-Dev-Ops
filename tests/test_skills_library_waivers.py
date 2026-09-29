"""Review round 12 P1-EXACT-EXAMPLE-WAIVER-ACCEPTS-LITERAL-PASSWORD: a waiver keyed on text alone
let that exact text pass as a literal password anywhere. A waiver is one reviewed file, line and
text, so the same text in any other place is flagged."""
from scripts import sync_skills_library as sync
from tests.test_skills_library_sync import _check, held_back, layout, library  # noqa: F401


def _flagged(lay):
    return any(p.startswith("secret-shaped") for p in _check(lay))


def test_a_waiver_covers_one_file_and_line_only(layout, monkeypatch):  # noqa: F811
    notes = layout["dest"] / "alpha" / "references" / "contract.md"
    text = 'PWD="$' + 'MYSQLPASSWORD"'
    notes.write_text("MYSQL_" + text + "\n")
    assert _flagged(layout), "the waived text in a file the waiver does not name"
    notes.write_text("const password = '" + text + "';\n")
    assert _flagged(layout), "round 12: the waived text as a literal password"
    notes.write_text("Example: AWS_KEY=" + "AKIA" + "IOSFODNN7EXAMPLE" + "\n")
    assert _flagged(layout), "no text is waived on its own, a vendor example included"
    monkeypatch.setattr(sync, "_WAIVED", frozenset({("alpha/references/contract.md", 1, text)}))
    notes.write_text("MYSQL_" + text + "\n")
    assert not _flagged(layout), "the waiver's own file, line and text"
    notes.write_text("\nMYSQL_" + text + "\n")
    assert _flagged(layout), "the same text moved to another line"


def test_every_waiver_names_a_real_line_of_the_copy():
    """A waiver whose line changed on a re-sync must be re-reviewed, not silently kept."""
    for rel, number, text in sync._WAIVED:
        lines = (sync.DEST / rel).read_text("utf-8").split("\n")
        assert text in lines[number - 1], (rel, number)
