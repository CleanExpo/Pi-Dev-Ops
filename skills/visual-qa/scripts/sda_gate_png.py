"""Strict PNG byte/decode checks for SDA source-bound browser evidence."""
import struct
import zlib

MAX_PNG_DECODED = 128 * 1024 * 1024


def _png_header(payload):
    if len(payload) != 13:
        raise ValueError("duplicate or invalid PNG header")
    w, h, depth, color, compression, filtering, interlace = struct.unpack(">IIBBBBB", payload)
    if w < 1 or h < 1 or depth != 8 or color not in (2, 6) or compression or filtering or interlace:
        raise ValueError("unexpected PNG image format")
    channels = 3 if color == 2 else 4
    if h * (1 + w * channels) > MAX_PNG_DECODED:
        raise ValueError("PNG decompression size exceeds limit")
    return w, h, channels


def _read_png_chunk(data, pos):
    """Read and CRC-verify one bounded PNG chunk without trusting its length."""
    n = struct.unpack(">I", data[pos:pos + 4])[0]
    if n > MAX_PNG_DECODED or pos + 12 + n > len(data):
        raise ValueError("damaged PNG chunk length")
    typ = data[pos + 4:pos + 8]
    payload = data[pos + 8:pos + 8 + n]
    checksum = struct.unpack(">I", data[pos + 8 + n:pos + 12 + n])[0]
    if (zlib.crc32(typ + payload) & 0xffffffff) != checksum:
        raise ValueError("PNG CRC mismatch")
    return typ, payload, pos + n + 12


def _png_chunks(data):
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("not a PNG")
    pos, dimensions, compressed, finished = 8, None, [], False
    idat_closed, palette_seen = False, False
    while pos + 12 <= len(data):
        typ, payload, pos = _read_png_chunk(data, pos)
        n = len(payload)
        if dimensions is None and typ != b"IHDR":
            raise ValueError("PNG header must be first")
        if compressed and typ != b"IDAT":
            idat_closed = True
        if typ == b"IDAT" and idat_closed:
            raise ValueError("nonconsecutive PNG image data")
        if typ == b"IHDR":
            if dimensions is not None:
                raise ValueError("duplicate or invalid PNG header")
            dimensions = _png_header(payload)
        elif typ == b"IDAT":
            if dimensions is None:
                raise ValueError("PNG image data before header")
            compressed.append(payload)
        elif typ == b"IEND":
            if n != 0 or pos != len(data):
                raise ValueError("invalid PNG ending or trailing bytes")
            finished = True
            break
        elif typ == b"PLTE":
            if compressed:
                raise ValueError("PNG palette after image data")
            if palette_seen:
                raise ValueError("duplicate PNG palette")
            palette_seen = True
        elif (typ[0] & 0x20) == 0:
            # Unknown critical chunks cannot be ignored by PNG decoders.
            raise ValueError("unsupported critical PNG chunk")
    if not finished or dimensions is None or not compressed:
        raise ValueError("incomplete PNG")
    return dimensions, compressed


def png_dimensions(data):
    """Decode RGB/RGBA PNG scanlines, not just magic bytes or headers."""
    (w, h, channels), compressed = _png_chunks(data)
    row = 1 + w * channels
    decompressor = zlib.decompressobj()
    try:
        raw = decompressor.decompress(b"".join(compressed), MAX_PNG_DECODED + 1)
    except zlib.error as exc:
        raise ValueError("PNG zlib decoder failed") from exc
    if (not decompressor.eof or decompressor.unused_data or decompressor.unconsumed_tail
            or len(raw) != row * h or any(raw[i * row] > 4 for i in range(h))):
        raise ValueError("PNG cannot be decoded into complete valid scanlines")
    return w, h
