"""Verify sync_wiki_to_supabase.py recurses into subdirs and uses relative path as id."""
import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parent.parent / "scripts" / "sync_wiki_to_supabase.py"


def _load():
    spec = importlib.util.spec_from_file_location("syncmod", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_sync_uses_rglob_not_glob(tmp_path, monkeypatch):
    mod = _load()
    wiki = tmp_path / "Wiki"
    (wiki / "plaud").mkdir(parents=True)
    (wiki / "top.md").write_text("# Top\n\nbody\n")
    (wiki / "plaud" / "nested.md").write_text("# Nested\n\nbody\n")

    monkeypatch.setattr(mod, "WIKI_DIR", wiki)
    monkeypatch.setattr(mod, "get_service_key", lambda: "fake-key")

    seen_ids: list[str] = []

    def fake_upsert(key, page_id, title, content, tags):
        seen_ids.append(page_id)
        return 201

    monkeypatch.setattr(mod, "upsert_page", fake_upsert)
    mod.main()

    assert "top" in seen_ids
    assert "plaud/nested" in seen_ids
