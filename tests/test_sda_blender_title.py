"""Pure checks for the SDA title card. Blender itself is not required."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills-library" / "skills" / "sda-video" / "scripts" / "blender_title.py"


def _load():
    import sys

    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec = importlib.util.spec_from_file_location("sda_blender_title", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.dont_write_bytecode = previous


def test_default_frame_is_native_vertical() -> None:
    title = _load()
    args = title.parse_args(["--", "--text", "One card. | Every link.", "--out", "insert-1.mp4"])
    assert (args.width, args.height) == (2160, 3840)
    assert title.lines_of(args.text) == "One card.\nEvery link."


def test_type_fits_eighty_percent_of_the_frame() -> None:
    title = _load()
    frame_w, frame_h = title.frame_span(2160, 3840)
    scale = title.fit_scale(measured_w=20, measured_h=2, frame_w=frame_w, frame_h=frame_h)
    assert scale == (frame_w * 0.8) / 20
    tall = title.fit_scale(measured_w=2, measured_h=100, frame_w=frame_w, frame_h=frame_h)
    assert tall == (frame_h * 0.8) / 100


def test_brand_colours_are_six_digit_hex() -> None:
    title = _load()
    assert title.rgb("0F2742") == (15 / 255, 39 / 255, 66 / 255, 1.0)
    assert title.rgb("#F26B1D")[0] == 0xF2 / 255
    with pytest.raises(ValueError):
        title.rgb("blue")
