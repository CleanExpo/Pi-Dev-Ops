#!/usr/bin/env python3
"""Prod image adapter for brand-video: generate one styled illustration via the
Gemini 'nano-banana' image model over plain HTTPS (works server-side, unlike the
local margot MCP). Same model family that produced the validated look.

Usage:  GEMINI_API_KEY=... python3 image_gen.py "<full prompt>" out.png
Import: from image_gen import generate_image; generate_image(prompt, out_path)
"""
import os, sys, json, base64, urllib.request, urllib.error

MODEL = os.environ.get("BRAND_VIDEO_IMAGE_MODEL", "gemini-2.5-flash-image")
ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={k}"

def generate_image(prompt: str, out_path: str) -> str:
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("IMAGE_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY (or IMAGE_API_KEY) not set")
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseModalities": ["IMAGE"],
                             "imageConfig": {"aspectRatio": os.environ.get("BRAND_VIDEO_ASPECT", "16:9")}},
    }).encode()
    import time
    last = ""
    for attempt in range(6):
        req = urllib.request.Request(
            ENDPOINT.format(m=MODEL, k=key), data=body, method="POST",
            headers={"content-type": "application/json"})
        try:
            resp = urllib.request.urlopen(req, timeout=120)
            data = json.loads(resp.read())
            break
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}: {e.read().decode()[:200]}"
            if e.code in (429, 500, 503) and attempt < 5:
                time.sleep(min(2 ** attempt, 30)); continue
            raise RuntimeError(f"image API {last}")
        except (urllib.error.URLError, TimeoutError) as e:
            last = str(e)
            if attempt < 5:
                time.sleep(min(2 ** attempt, 30)); continue
            raise RuntimeError(f"image API {last}")
    else:
        raise RuntimeError(f"image API exhausted retries: {last}")
    for part in data["candidates"][0]["content"]["parts"]:
        inline = part.get("inlineData") or part.get("inline_data")
        if inline and inline.get("data"):
            with open(out_path, "wb") as f:
                f.write(base64.b64decode(inline["data"]))
            return out_path
    raise RuntimeError(f"no image in response: {json.dumps(data)[:400]}")

if __name__ == "__main__":
    out = generate_image(sys.argv[1], sys.argv[2])
    print("wrote", out)
