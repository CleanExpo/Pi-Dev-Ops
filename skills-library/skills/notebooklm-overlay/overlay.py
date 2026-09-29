"""
notebooklm-overlay: composite the locked Unite-Group editorial cards onto a
base render produced by the video-use skill.

Usage:
    python overlay.py --input base.mp4 --beats beats.json --output final.mp4

The beats.json schema is documented in the sibling SKILL.md.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


CHARTER = "/System/Library/Fonts/Supplemental/Charter.ttc"

THEME = {
    "card_bg":  (250, 249, 246, 235),
    "rule":     (40, 40, 40, 220),
    "title_fg": (20, 20, 20, 255),
    "body_fg":  (60, 60, 60, 255),
}

CARD_W = 1920
CARD_H = 220
PAD_X = 96
FADE_S = 0.3


def _fonts():
    title = ImageFont.truetype(CHARTER, 42, index=1)  # Charter italic
    body = ImageFont.truetype(CHARTER, 24, index=0)   # Charter regular
    return title, body


def render_card(title: str, body_lines: list[str], out_path: Path) -> None:
    img = Image.new("RGBA", (CARD_W, CARD_H), THEME["card_bg"])
    draw = ImageDraw.Draw(img)
    title_font, body_font = _fonts()

    draw.line([(PAD_X, 2), (CARD_W - PAD_X, 2)], fill=THEME["rule"], width=2)

    draw.text((PAD_X, 36), title, font=title_font, fill=THEME["title_fg"])

    body_y = 100
    for line in body_lines:
        draw.text((PAD_X, body_y), line, font=body_font, fill=THEME["body_fg"])
        body_y += 36

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)


def build_ffmpeg_cmd(
    input_video: Path,
    beats: list[dict],
    card_paths: list[Path],
    output: Path,
) -> list[str]:
    cmd: list[str] = ["ffmpeg", "-y", "-i", str(input_video)]

    for beat, card in zip(beats, card_paths):
        duration = beat["window"][1] - beat["window"][0]
        cmd += ["-loop", "1", "-t", f"{duration:.3f}", "-i", str(card)]

    filters: list[str] = []

    # PTS-shift + fade each card to its window
    for i, beat in enumerate(beats, start=1):
        start, end = beat["window"]
        dur = end - start
        fade_out_st = max(0.0, dur - FADE_S)
        filters.append(
            f"[{i}:v]format=rgba,"
            f"fade=t=in:st=0:d={FADE_S}:alpha=1,"
            f"fade=t=out:st={fade_out_st:.3f}:d={FADE_S}:alpha=1,"
            f"setpts=PTS+{start:.3f}/TB"
            f"[c{i}]"
        )

    # Chain overlays
    prev_label = "[0:v]"
    for i, beat in enumerate(beats, start=1):
        start, end = beat["window"]
        is_last = i == len(beats)
        out_label = "[vout]" if is_last else f"[v{i}]"
        filters.append(
            f"{prev_label}[c{i}]overlay=x=0:y=H-h:"
            f"enable='between(t,{start:.3f},{end:.3f})'"
            f"{out_label}"
        )
        prev_label = out_label

    cmd += [
        "-filter_complex", ";".join(filters),
        "-map", "[vout]",
        "-map", "0:a",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        "-movflags", "+faststart",
        str(output),
    ]
    return cmd


def main() -> None:
    ap = argparse.ArgumentParser(description="Apply Unite-Group editorial overlay to a NotebookLM video")
    ap.add_argument("--input", required=True, type=Path, help="Base MP4 (from video-use, --no-subtitles)")
    ap.add_argument("--beats", required=True, type=Path, help="beats.json (see SKILL.md)")
    ap.add_argument("--output", required=True, type=Path, help="Output MP4 path")
    ap.add_argument("--keep-cards", action="store_true", help="Keep rendered PNG cards next to output (for debugging)")
    args = ap.parse_args()

    if not args.input.exists():
        sys.exit(f"input not found: {args.input}")
    if not args.beats.exists():
        sys.exit(f"beats config not found: {args.beats}")

    beats_spec = json.loads(args.beats.read_text())
    beats = beats_spec["beats"]

    if args.keep_cards:
        cards_dir = args.output.parent / f"{args.output.stem}_cards"
        cards_dir.mkdir(parents=True, exist_ok=True)
        ctx = None
    else:
        ctx = tempfile.TemporaryDirectory()
        cards_dir = Path(ctx.name)

    try:
        card_paths: list[Path] = []
        for i, beat in enumerate(beats, start=1):
            p = cards_dir / f"card_{i}.png"
            render_card(beat["title"], beat["body"], p)
            card_paths.append(p)
            print(f"  card {i}: {beat['title']!r}  ({beat['window'][1] - beat['window'][0]:.2f}s)")

        cmd = build_ffmpeg_cmd(args.input, beats, card_paths, args.output)
        print(f"compositing {len(beats)} overlays...")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            sys.stderr.write(result.stderr)
            sys.exit(result.returncode)
        print(f"done: {args.output}")
    finally:
        if ctx is not None:
            ctx.cleanup()


if __name__ == "__main__":
    main()
