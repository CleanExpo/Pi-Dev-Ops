"""Actual FFprobe/FFmpeg verified film frames, audio timelines and captions."""
import math
import subprocess
import tempfile
from pathlib import Path

from sda_gate_core import (
    MAX_AUDIO_END_DRIFT_SECONDS, MAX_AV_START_OFFSET_SECONDS,
    REQUIRED_FRAME_TIMES, _validate_srt, strict_json,
)
from sda_gate_png import png_dimensions


def _restricted_media_input(snapshot):
    # The verified hash proves bytes, not that a playlist is safe to open.
    # Never auto-detect HLS/concat or permit FFmpeg to fetch network inputs.
    # MOV external data references remain disabled, including absolute paths.
    return ["-protocol_whitelist", "file", "-f", "mov",
            "-enable_drefs", "0", "-use_absolute_path", "0",
            "-i", str(snapshot)]


def _validate_mp4_bytes(data):
    # Fail before launching FFmpeg on untrusted manifests or playlists.
    if len(data) < 16 or data[4:8] != b"ftyp":
        raise ValueError("master must be an ISO BMFF/MP4 container")
    length = int.from_bytes(data[:4], "big")
    if length < 16 or length > min(len(data), 4096) or length % 4:
        raise ValueError("master has an invalid ISO BMFF/MP4 file-type box")


def _frame_timestamps(frames, errors):
    if not isinstance(frames, list):
        errors.append("film.frames must be an array")
        frames = []
    times = {f["second"] for f in frames if isinstance(f, dict) and
             type(f.get("second")) is int}
    if len(times) != len(frames) or (times - REQUIRED_FRAME_TIMES):
        errors.append("malformed, duplicate or unexpected frame timestamps")
    for second in sorted(REQUIRED_FRAME_TIMES - times):
        errors.append("missing film-frame inspection at " + str(second) + "s")
    if len(frames) != len(times):
        errors.append("duplicate or malformed film-frame timestamps")
    return frames, times


def _read_frames(frames, asset, errors):
    frame_data = {}
    for entry in frames:
        if not isinstance(entry, dict):
            errors.append("frame must be an object")
            continue
        second = entry.get("second")
        if type(second) is not int or second not in REQUIRED_FRAME_TIMES:
            errors.append("frame has an invalid inspection timestamp")
            continue
        inspected = asset(entry.get("file"), entry.get("sha256"), "frame " + str(second))
        if inspected:
            try:
                frame_dimensions = png_dimensions(inspected[1])
                frame_data[second] = (inspected[1], frame_dimensions)
            except ValueError as exc:
                errors.append("frame " + str(second) + ": PNG cannot decode: " + str(exc))
    return frame_data


def _probe(snapshot):
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=codec_type,width,height,start_time,duration,channels,sample_rate:format=duration",
         "-of", "json", *_restricted_media_input(snapshot)],
        capture_output=True, text=True, timeout=25,
    )
    if probe.returncode != 0:
        raise ValueError("ffprobe rejected master: " + probe.stderr[-200:])
    return strict_json(probe.stdout)


def _select_streams(info):
    videos = [x for x in info.get("streams", []) if x.get("codec_type") == "video"]
    if not videos:
        raise ValueError("master has no playable video stream")
    audios = [x for x in info.get("streams", []) if x.get("codec_type") == "audio"]
    if not audios:
        raise ValueError("master has no actual audio stream")
    others = [x for x in info.get("streams", []) if x.get("codec_type") not in ("video", "audio")]
    if any(x.get("codec_type") == "subtitle" for x in others):
        raise ValueError("embedded subtitle tracks unsupported without independent caption verification")
    if others:
        raise ValueError("unverified non-audio/video tracks must be removed or verified")
    # Fail closed until every retained output track can be inspected.
    # Do not let a good primary audio track conceal an unverified alternate.
    if len(videos) != 1 or len(audios) != 1:
        raise ValueError("multiple audio/video streams not independently verified")
    return videos[0], audios[0]


def _validate_stream_timelines(info, video, audio):
    width, height = video["width"], video["height"]
    duration = float(video.get("duration", "nan"))
    container_duration = float(info["format"]["duration"])
    vstart = float(video.get("start_time", "nan"))
    astart = float(audio.get("start_time", "nan"))
    aduration = float(audio.get("duration", "nan"))
    sample_rate = int(audio.get("sample_rate", 0))
    channels = int(audio.get("channels", 0))
    if not all(math.isfinite(t) for t in (duration, container_duration, vstart, astart, aduration)) or duration <= 0 or container_duration <= 0:
        raise ValueError("master audio/video timestamps not finite")
    if sample_rate < 16000 or channels < 1:
        raise ValueError("master audio stream is not usable narration/music")
    if abs(vstart - astart) > MAX_AV_START_OFFSET_SECONDS:
        raise ValueError("audio/video stream start offset over 100 ms")
    if abs(vstart) > MAX_AV_START_OFFSET_SECONDS:
        raise ValueError("master stream start is delayed relative to container timeline")
    if abs((astart + aduration) - (vstart + duration)) > MAX_AUDIO_END_DRIFT_SECONDS:
        raise ValueError("audio stream ends too early/late relative to video")
    if abs(container_duration - (vstart + duration)) > 0.55:
        raise ValueError("master container timeline differs from video end")
    return width, height, duration


def _validate_master_duration(film, duration):
    target = film.get("expected_duration_seconds")
    if (type(target) not in (float, int) or not math.isfinite(target) or
            target < max(REQUIRED_FRAME_TIMES) + 1):
        raise ValueError("manifest expected_duration_seconds missing/too short")
    if abs(duration - target) > 0.55:
        raise ValueError("master duration does not match requested duration")


def _decode_master(snapshot):
    full = subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-xerror",
         "-err_detect", "explode", *_restricted_media_input(snapshot),
         "-map", "0:v:0", "-map", "0:a:0", "-f", "null", "-"],
        capture_output=True, timeout=180,
    )
    # FFmpeg can conceal corrupted media by recovering and exiting 0.
    # Never approve a master if the complete decode reported any error.
    if full.returncode != 0 or full.stderr.strip():
        raise ValueError("master complete audio/video decode failed: " +
                         full.stderr[-200:].decode("utf-8", "replace"))


def _compare_frames(snapshot, frame_data, times, width, height, errors):
    for second in sorted(REQUIRED_FRAME_TIMES & times):
        if second not in frame_data:
            continue
        exported = subprocess.run(
            ["ffmpeg", "-nostdin", "-v", "error", "-ss", str(second),
             *_restricted_media_input(snapshot), "-frames:v", "1", "-f", "image2pipe",
             "-c:v", "png", "pipe:1"], capture_output=True, timeout=35,
        )
        claimed_bytes, claimed_dimensions = frame_data[second]
        # FFmpeg auto-applies MP4 display rotation when exporting a PNG.
        # Its exact bytes, already decoded as valid PNG in _read_frames, are
        # the authority. Coded stream dimensions can have swapped axes.
        if exported.returncode != 0 or exported.stdout != claimed_bytes:
            errors.append("frame " + str(second) +
                          ": supplied bytes not actual FFmpeg master frame")


def _inspect_master(master, film, captions, frame_data, times, errors):
    try:
        _validate_mp4_bytes(master[1])
        with tempfile.TemporaryDirectory(prefix="sda-verified-media-") as temp:
            snapshot = Path(temp) / "master.mp4"
            snapshot.write_bytes(master[1])
            info = _probe(snapshot)
            video, audio = _select_streams(info)
            width, height, duration = _validate_stream_timelines(info, video, audio)
            if captions:
                try:
                    _validate_srt(captions[1], duration)
                except ValueError as exc:
                    errors.append("master caption timestamps invalid: " + str(exc))
            _validate_master_duration(film, duration)
            _decode_master(snapshot)
            _compare_frames(snapshot, frame_data, times, width, height, errors)
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired) as exc:
        errors.append("master media decode/provenance invalid: " + str(exc)[:260])


def validate_film(doc, asset, errors):
    film = doc.get("film") or {}
    if not isinstance(film, dict):
        errors.append("film must be an object")
        film = {}
    master = asset(film.get("file"), film.get("sha256"), "master film")
    captions = asset(film.get("captions_file"), film.get("captions_sha256"), "master captions")
    frames, times = _frame_timestamps(film.get("frames") or [], errors)
    frame_data = _read_frames(frames, asset, errors)
    if master:
        _inspect_master(master, film, captions, frame_data, times, errors)
