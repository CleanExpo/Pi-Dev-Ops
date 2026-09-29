#!/usr/bin/env python3
"""stitch_vertical.py <slug> — like stitch.py but renders 1080x1920 (9:16) for
short-form (Reels/TikTok/Shorts). One image per beat; even-split fallback if
counts differ. Run AFTER tts.py + 9:16 image generation."""
import sys, os, json, glob, subprocess
slug = sys.argv[1]
beats = json.load(open(f"{slug}/transcript.json"))
imgs = sorted(glob.glob(f"{slug}/images/*.png"))
if not imgs: sys.exit(f"{slug}: no images")
vo = f"{slug}/voiceover.mp3"
vodur = float(subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",vo]).strip())
n = len(imgs)
starts = [b["start"] for b in beats] if n == len(beats) else [i*vodur/n for i in range(n)]
starts.append(vodur)
lines=[]
for i,img in enumerate(imgs):
    dur=round(max(0.4, starts[i+1]-starts[i]),3)
    lines.append(f"file '{os.path.relpath(img, slug)}'"); lines.append(f"duration {dur}")
lines.append(f"file '{os.path.relpath(imgs[-1], slug)}'")
open(f"{slug}/list.txt","w").write("\n".join(lines)+"\n")
subprocess.check_call(["ffmpeg","-y","-loglevel","error","-f","concat","-safe","0","-i",f"{slug}/list.txt",
  "-i",vo,"-vf","scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=25,format=yuv420p",
  "-c:v","libx264","-preset","medium","-crf","19","-c:a","aac","-b:a","192k","-shortest",f"{slug}/final-vertical.mp4"])
fd=subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",f"{slug}/final-vertical.mp4"]).strip().decode()
print(f"{slug}: rendered {slug}/final-vertical.mp4 ({fd}s, {n} imgs, {len(beats)} beats, 1080x1920)")
