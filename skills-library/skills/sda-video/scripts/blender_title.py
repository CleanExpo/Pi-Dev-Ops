"""Render a 9:16 3D kinetic title insert in Blender, headless.

Run:
  ~/Applications/Blender.app/Contents/MacOS/Blender -b --python blender_title.py -- \
      --text "One card. Every link." --hex 0F2742 --accent F26B1D \
      --seconds 3 --fps 30 --out /path/title.mp4

The text is real geometry (extruded, bevelled, chrome-lit), so no model ever draws
letters. Logos are never built here: composite the approved logo file in the edit.
"""
import argparse
import sys

import bpy


def hex_rgba(h):
    h = h.lstrip('#')
    srgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in srgb]
    return (*lin, 1.0)


def args():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument('--text', required=True)
    p.add_argument('--hex', default='0F2742', help='background colour')
    p.add_argument('--accent', default='F26B1D', help='rim light colour')
    p.add_argument('--seconds', type=float, default=3.0)
    p.add_argument('--fps', type=int, default=30)
    p.add_argument('--width', type=int, default=1080)
    p.add_argument('--height', type=int, default=1920)
    p.add_argument('--out', required=True)
    return p.parse_args(argv)


def main():
    a = args()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_EEVEE_NEXT'
    scene.render.resolution_x, scene.render.resolution_y = a.width, a.height
    scene.render.fps = a.fps
    scene.frame_start, scene.frame_end = 1, max(2, round(a.seconds * a.fps))
    scene.render.image_settings.file_format = 'FFMPEG'
    scene.render.ffmpeg.format = 'MPEG4'
    scene.render.ffmpeg.codec = 'H264'
    scene.render.ffmpeg.constant_rate_factor = 'HIGH'
    scene.render.filepath = a.out

    world = bpy.data.worlds.new('bg')
    world.use_nodes = True
    world.node_tree.nodes['Background'].inputs[0].default_value = hex_rgba(a.hex)
    scene.world = world

    bpy.ops.object.text_add(location=(0, 0, 0))
    txt = bpy.context.object
    txt.data.body = a.text.replace(' | ', '\n')
    txt.data.align_x, txt.data.align_y = 'CENTER', 'CENTER'
    txt.data.extrude, txt.data.bevel_depth, txt.data.size = 0.12, 0.02, 0.9
    chrome = bpy.data.materials.new('chrome')
    chrome.use_nodes = True
    bsdf = chrome.node_tree.nodes['Principled BSDF']
    bsdf.inputs['Base Color'].default_value = (0.9, 0.92, 0.95, 1.0)
    bsdf.inputs['Metallic'].default_value = 0.85
    bsdf.inputs['Roughness'].default_value = 0.28
    txt.data.materials.append(chrome)

    # Fit the widest line to 80% of the frame width at the closest camera distance.
    bpy.context.view_layer.update()
    near, sensor, lens = 7.5, 36.0, 50.0
    visible_w = near * sensor / lens * min(1.0, a.width / a.height)
    s = 0.8 * visible_w / max(txt.dimensions.x, 1e-6)
    txt.scale = (s, s, s)

    # Slow push-in with a small turn: hold-friendly pacing, no whip moves.
    end = scene.frame_end
    txt.rotation_euler = (1.45, 0, -0.25)
    txt.keyframe_insert('rotation_euler', frame=1)
    txt.rotation_euler = (1.5708, 0, 0)
    txt.keyframe_insert('rotation_euler', frame=max(2, int(end * 0.6)))

    bpy.ops.object.camera_add(location=(0, -9, 0), rotation=(1.5708, 0, 0))
    cam = bpy.context.object
    scene.camera = cam
    cam.keyframe_insert('location', frame=1)
    cam.location = (0, -7.5, 0)
    cam.keyframe_insert('location', frame=end)

    bpy.ops.object.light_add(type='AREA', location=(-3, -5, 4))
    key = bpy.context.object.data
    key.energy, key.size = 2500, 4
    bpy.ops.object.light_add(type='AREA', location=(0, -6, -3))
    bpy.context.object.data.energy = 1200
    bpy.ops.object.light_add(type='AREA', location=(4, 2, 1))
    rim = bpy.context.object.data
    rim.energy, rim.color = 1400, hex_rgba(a.accent)[:3]

    bpy.ops.render.render(animation=True)
    print('BLENDER_TITLE_OK', a.out, scene.frame_end, 'frames')


main()
