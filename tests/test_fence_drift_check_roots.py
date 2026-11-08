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
    (tmp_path / "x.py").write_text('u = "abcdefghijklmnopqrst.supabase.co"\n')
    monkeypatch.setattr(mod, "CODE_ROOTS", [str(tmp_path)])
    refs, err = mod.code_refs()
    assert err is None
    assert list(refs) == ["abcdefghijklmnopqrst"]


def test_no_roots_still_reports_unchecked(monkeypatch):
    mod = _load()
    monkeypatch.setattr(mod, "CODE_ROOTS", [])
    refs, err = mod.code_refs()
    assert refs == {} and err and "no code roots" in err


def test_env_roots_added(tmp_path, monkeypatch):
    monkeypatch.setenv("FENCE_CODE_ROOTS", str(tmp_path))
    assert str(tmp_path) in _load().find_code_roots()
