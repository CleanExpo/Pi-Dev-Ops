"""Sync check cases added after the library made a shared folder a skill too (library bb57abf2)."""
import json

from tests.test_skills_library_sync import _check, _resync, held_back, layout, library  # noqa: F401 (fixtures)


def test_a_shared_folder_that_is_also_a_library_skill_is_copied_and_clean(layout):  # noqa: F811 (fixture)
    """Library bb57abf2 made `library` (a shared _EXTRAS folder) a home=library skill too. The
    check excluded every _EXTRAS name from the copied set, so it reported the copied skill as
    'home=library but not copied: library'."""
    lib = layout["library"] / "skills"
    (lib / "library" / "SKILL.md").write_text("---\nname: library\ndescription: Routes connections.\n---\nBody.\n")
    homes = json.loads((lib / "HOMES.json").read_text())
    homes["homes"]["library"] = "library"
    (lib / "HOMES.json").write_text(json.dumps(homes))
    _resync(layout)
    assert (layout["dest"] / "library" / "SKILL.md").is_file()
    assert _check(layout) == []
    (layout["dest"] / "library" / "SKILL.md").write_text("---\nname: other\ndescription: x\n---\n")
    assert any("library" in p for p in _check(layout))
