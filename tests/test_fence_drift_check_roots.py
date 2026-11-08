"""The fence drift code sweep must have a root on a machine with no D:\\ drive (CI)."""
import importlib.util
import pathlib

SRC = pathlib.Path(__file__).resolve().parent.parent / "fence" / "drift_check.py"


def _load():
    spec = importlib.util.spec_from_file_location("drift_check_under_test", SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_checkout_is_always_a_code_root():
    mod = _load()
    assert mod.REPO_ROOT in mod.find_code_roots()


def test_sweep_is_checkable_without_d_drive(tmp_path, monkeypatch):
    mod = _load()
    ref = "abcdefghij" + "klmnopqrst"  # split so this file holds no ref-shaped literal for the sweep
    (tmp_path / "x.py").write_text(f'u = "{ref}.supabase.co"\n')
    monkeypatch.setattr(mod, "CODE_ROOTS", [str(tmp_path)])
    refs, err = mod.code_refs()
    assert err is None
    assert list(refs) == [ref]


def test_no_roots_still_reports_unchecked(monkeypatch):
    mod = _load()
    monkeypatch.setattr(mod, "CODE_ROOTS", [])
    refs, err = mod.code_refs()
    assert refs == {} and err and "no code roots" in err


def test_env_roots_added(tmp_path, monkeypatch):
    monkeypatch.setenv("FENCE_CODE_ROOTS", str(tmp_path))
    assert str(tmp_path) in _load().find_code_roots()


def test_this_checkout_names_no_supabase_ref_missing_from_the_fence(monkeypatch):
    """The scheduled check sweeps this checkout. Any ref-shaped literal added here (a test
    fixture included) that fence.json does not list would turn that check red by itself."""
    import json
    mod = _load()
    monkeypatch.setattr(mod, "CODE_ROOTS", [mod.REPO_ROOT])
    refs, err = mod.code_refs()
    assert err is None
    prod = json.loads(mod.FENCE_FILE.read_text(encoding="utf-8")).get("prod", {})
    inventory = {d.lower() for d in prod.get("databases", []) if isinstance(d, str)}
    inventory |= {e.lower() for e in prod.get("_databases_excluded_preview_branches", [])}
    stray = {ref: files for ref, files in refs.items() if ref.lower() not in inventory}
    assert stray == {}
