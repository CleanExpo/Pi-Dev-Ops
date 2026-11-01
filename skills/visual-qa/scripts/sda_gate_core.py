"""SDA evidence constants, bounded no-follow I/O and strict subtitle parsing."""
import hashlib
import json
import os
import re
import stat
from pathlib import Path

RUBRIC = {
    "hierarchy": 20, "readability_contrast": 15,
    "art_direction_originality": 20, "motion_pacing": 15,
    "brand_fidelity": 10, "responsive_mobile": 10, "authenticity_rights": 10,
}
VIEWPORTS = {"mobile": (390, 844), "tablet": (768, 1024), "desktop": (1440, 900)}
REQUIRED_VIEWPORTS = set(VIEWPORTS)
REQUIRED_FRAME_TIMES = {0, 5, 10, 15, 20, 30, 45, 55, 59}
MAX_AV_START_OFFSET_SECONDS = 0.100
MAX_AUDIO_END_DRIFT_SECONDS = 0.250
SRT_TIMECODE = re.compile(r"^(\d{2}):(\d{2}):(\d{2}),(\d{3})$")
MAX_PNG_DECODED = 128 * 1024 * 1024
MAX_MEDIA_BYTES = 256 * 1024 * 1024  # fail closed rather than duplicate huge masters on the coding SSD
HASH = re.compile(r"[0-9a-f]{64}")


def strict_json(source):
    """Refuse non-standard JSON NaN and Infinity before any rubric maths."""
    def invalid(value):
        raise ValueError("non-finite JSON number: " + value)
    return json.loads(source, parse_constant=invalid)


def _pinned_root_dir(root):
    """Open every root ancestor via O_NOFOLLOW from /, not by absolute os.open."""
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise OSError("secure directory descriptor operations unavailable")
    if not root.is_absolute():
        raise ValueError("evidence root must be absolute")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open("/", flags)
    try:
        for component in root.parts[1:]:
            next_fd = os.open(component, flags, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        return fd
    except BaseException:
        os.close(fd)
        raise


def _read_held_file(rootfd, parts, cap, with_identity=False):
    """Read one regular file under a pinned directory without following symlinks."""
    fds = []
    try:
        parentfd = rootfd
        for component in parts[:-1]:
            childfd = os.open(
                component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=parentfd,
            )
            fds.append(childfd)
            parentfd = childfd
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parentfd)
        fds.append(fd)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > cap:
            raise ValueError("evidence is not a regular file or exceeds cap")
        chunks = []
        size = 0
        while True:
            data = os.read(fd, min(1024 * 1024, cap + 1 - size))
            if not data:
                break
            size += len(data)
            if size > cap:
                raise ValueError("evidence grew beyond cap")
            chunks.append(data)
        payload = b"".join(chunks)
        return (payload, (info.st_dev, info.st_ino)) if with_identity else payload
    finally:
        for fd in reversed(fds):
            os.close(fd)

def _srt_seconds(value):
    m = SRT_TIMECODE.fullmatch(value)
    if not m:
        raise ValueError("caption timecode malformed: " + value[:24])
    hours, minutes, seconds, millis = map(int, m.groups())
    if minutes >= 60 or seconds >= 60:
        raise ValueError("caption timecode invalid clock value")
    return hours * 3600 + minutes * 60 + seconds + millis / 1000


def _validate_srt(payload, duration):
    try:
        source = payload.decode("utf-8-sig").replace("\r\n", "\n").strip()
    except UnicodeDecodeError as exc:
        raise ValueError("caption text must be UTF-8") from exc
    if not source:
        raise ValueError("caption file is empty")
    blocks = re.split(r"\n[ \t]*\n", source)
    previous_end = 0.
    for index, block in enumerate(blocks, 1):
        lines = [x.strip() for x in block.splitlines()]
        if len(lines) < 3 or lines[0] != str(index):
            raise ValueError("caption block numbering/text missing")
        if " --> " not in lines[1]:
            raise ValueError("caption block timing missing")
        begin, end = lines[1].split(" --> ", 1)
        start_sec, end_sec = _srt_seconds(begin), _srt_seconds(end)
        if not previous_end <= start_sec < end_sec <= duration + .100:
            raise ValueError("caption timing overlaps or extends outside actual master")
        if not any(lines[2:]):
            raise ValueError("caption block empty")
        # Detect extra cue headers/timings hiding in text when an SRT blank
        # separator was omitted. A cue cannot silently absorb a second cue.
        for pos, line in enumerate(lines[2:], 2):
            if (line.isdecimal() and pos + 1 < len(lines) and
                    "-->" in lines[pos + 1]):
                raise ValueError("caption cue missing blank separator or malformed second timing")
            if re.match(r"^\d{2}:\d{2}:\d{2},\d{3}\s*-->", line):
                raise ValueError("caption embedded timing cannot be cue text")
        previous_end = end_sec
    return len(blocks)


class EvidenceAssets:
    def __init__(self, rootfd, errors):
        self.rootfd = rootfd
        self.errors = errors

    def __call__(self, rel, expected_sha, label):
        """Hash bytes from an O_NOFOLLOW, directory-fd-confined open.

        No pathname re-open is permitted after checking containment: each
        directory and the final evidence file are opened relative to the
        already-held trusted parent descriptor. A concurrent symlink swap
        cannot redirect the read outside the evidence root.
        """
        if (not isinstance(rel, str) or not rel or
                not isinstance(expected_sha, str) or not HASH.fullmatch(expected_sha)):
            self.errors.append(label + ": missing or invalid evidence path/SHA256")
            return None
        relative = Path(rel)
        parts = rel.split("/")
        if (relative.is_absolute() or "\\" in rel or
                any(part in ("", ".", "..") for part in parts)):
            self.errors.append(label + ": noncanonical/path traversal evidence filename")
            return None
        if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
            self.errors.append(label + ": secure no-follow directory operations unavailable")
            return None
        try:
            cap = MAX_MEDIA_BYTES if label == "master film" else MAX_PNG_DECODED * 2
            payload, identity = _read_held_file(self.rootfd, parts, cap, with_identity=True)
        except (OSError, ValueError) as exc:
            self.errors.append(label + ": evidence file unreadable or escaped root: " + str(exc))
            return None
        if hashlib.sha256(payload).hexdigest() != expected_sha:
            self.errors.append(label + ": SHA256 mismatch: " + rel)
            return None
        return relative, payload, identity
