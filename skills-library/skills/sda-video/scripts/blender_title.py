"""Brand title card for the SDA chain. Run it with Blender, not system Python.

Blender -b --python blender_title.py -- --text "One card. | Every link." \\
    --hex 0F2742 --accent F26B1D --seconds 3 --out insert-1.mp4

Default frame is 2160x3840. Pass --width and --height for square or widescreen.
``|`` splits lines. The type is fitted to 80% of the frame width, and capped so
it also stays inside 80% of the frame height.
"""
from __future__ import annotations

import argparse
import sys

ORTHO_WIDTH = 10.0


def parse_args(argv: list[str]) -> argparse.Namespace:
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    parser = argparse.ArgumentParser(description="Render a brand title card")
    parser.add_argument("--text", required=True)
    parser.add_argument("--hex", default="0F2742")
    parser.add_argument("--accent", default="F26B1D")
    parser.add_argument("--seconds", type=float, default=3.0)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--width", type=int, default=2160)
    parser.add_argument("--height", type=int, default=3840)
    parser.add_argument("--out", required=True)
    return parser.parse_args(argv)


def rgb(hex_colour: str) -> tuple[float, float, float, float]:
    cleaned = hex_colour.strip().removeprefix("#")
    if len(cleaned) != 6 or any(c not in "0123456789abcdefABCDEF" for c in cleaned):
        raise ValueError(f"colour must be 6 hex digits, got {hex_colour!r}")
    channels = [int(cleaned[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    return (channels[0], channels[1], channels[2], 1.0)


def frame_span(width_px: int, height_px: int, ortho: float = ORTHO_WIDTH) -> tuple[float, float]:
    if width_px <= 0 or height_px <= 0:
        raise ValueError("frame width and height must be positive")
    return ortho, ortho * (height_px / width_px)


def fit_scale(measured_w: float, measured_h: float, frame_w: float, frame_h: float) -> float:
    """Scale so the type is 80% of the frame width, without exceeding 80% of the height."""
    if measured_w <= 0 or measured_h <= 0:
        return 1.0
    by_width = (frame_w * 0.8) / measured_w
    by_height = (frame_h * 0.8) / measured_h
    return min(by_width, by_height)


def lines_of(text: str) -> str:
    parts = [part.strip() for part in text.split("|")]
    body = "\n".join(part for part in parts if part)
    if not body:
        raise ValueError("text is empty")
    return body


def _set_input(node: object, names: tuple[str, ...], value: object) -> None:
    inputs = getattr(node, "inputs")
    for name in names:
        socket = inputs.get(name)
        if socket is not None:
            socket.default_value = value
            return


def _clear(bpy: object) -> None:
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)


def _world(bpy: object, colour: tuple[float, float, float, float]) -> None:
    world = bpy.data.worlds.new("TitleWorld")
    bpy.context.scene.world = world
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    _set_input(background, ("Color",), colour)


def _material(bpy: object, colour: tuple[float, float, float, float]) -> object:
    mat = bpy.data.materials.new("Accent")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    _set_input(bsdf, ("Base Color",), colour)
    _set_input(bsdf, ("Emission Color", "Emission"), colour)
    _set_input(bsdf, ("Emission Strength",), 1.0)
    return mat


def _text(bpy: object, body: str, colour: tuple[float, float, float, float], span: tuple[float, float]) -> None:
    curve = bpy.data.curves.new("Title", type="FONT")
    curve.body = body
    curve.align_x = "CENTER"
    curve.align_y = "CENTER"
    curve.size = 1.0
    obj = bpy.data.objects.new("Title", curve)
    bpy.context.scene.collection.objects.link(obj)
    obj.data.materials.append(_material(bpy, colour))
    bpy.context.view_layer.update()
    scale = fit_scale(obj.dimensions.x, obj.dimensions.y, span[0], span[1])
    obj.scale = (scale, scale, scale)


def _camera(bpy: object) -> None:
    data = bpy.data.cameras.new("TitleCam")
    data.type = "ORTHO"
    data.ortho_scale = ORTHO_WIDTH
    cam = bpy.data.objects.new("TitleCam", data)
    bpy.context.scene.collection.objects.link(cam)
    cam.location = (0.0, 0.0, 10.0)
    bpy.context.scene.camera = cam


def _scene(bpy: object, args: argparse.Namespace) -> None:
    scene = bpy.context.scene
    scene.render.resolution_x = args.width
    scene.render.resolution_y = args.height
    scene.render.resolution_percentage = 100
    scene.render.fps = args.fps
    scene.frame_start = 1
    scene.frame_end = max(1, round(args.seconds * args.fps))
    scene.render.image_settings.file_format = "FFMPEG"
    scene.render.ffmpeg.format = "MPEG4"
    scene.render.ffmpeg.codec = "H264"
    scene.render.filepath = args.out
    scene.view_settings.view_transform = "Standard"


def render(argv: list[str] | None = None) -> None:
    import bpy

    args = parse_args(sys.argv if argv is None else argv)
    _clear(bpy)
    _world(bpy, rgb(args.hex))
    _text(bpy, lines_of(args.text), rgb(args.accent), frame_span(args.width, args.height))
    _camera(bpy)
    _scene(bpy, args)
    bpy.ops.render.render(animation=True)


if __name__ == "__main__":
    render()
