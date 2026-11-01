"""Fail-closed PNG structural ordering for SDA screenshot evidence."""
import struct
import unittest
import zlib

from sda_gate_png import png_dimensions


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def chunk(kind, payload=b""):
    crc = zlib.crc32(kind + payload) & 0xffffffff
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", crc)


def components():
    header = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    data = zlib.compress(b"\x00\x00\x00\x00\xff")
    return chunk(b"IHDR", header), data, chunk(b"IEND")


class PNGOrderTests(unittest.TestCase):
    def test_valid_png_is_still_accepted(self):
        header, compressed, end = components()
        payload = PNG_SIGNATURE + header + chunk(b"IDAT", compressed) + end
        self.assertEqual(png_dimensions(payload), (1, 1))

    def test_ancillary_chunk_before_ihdr_is_rejected(self):
        header, compressed, end = components()
        payload = (PNG_SIGNATURE + chunk(b"tEXt", b"k\x00v") +
                   header + chunk(b"IDAT", compressed) + end)
        with self.assertRaisesRegex(ValueError, "PNG header must be first"):
            png_dimensions(payload)

    def test_interrupted_idat_sequence_is_rejected(self):
        header, compressed, end = components()
        mid = len(compressed) // 2
        payload = (PNG_SIGNATURE + header + chunk(b"IDAT", compressed[:mid]) +
                   chunk(b"tEXt", b"k\x00v") + chunk(b"IDAT", compressed[mid:]) + end)
        with self.assertRaisesRegex(ValueError, "nonconsecutive PNG image data"):
            png_dimensions(payload)

    def test_palette_after_idat_is_rejected(self):
        header, compressed, end = components()
        payload = (PNG_SIGNATURE + header + chunk(b"IDAT", compressed) +
                   chunk(b"PLTE", b"\x00\x00\x00") + end)
        with self.assertRaisesRegex(ValueError, "PNG palette after image data"):
            png_dimensions(payload)


if __name__ == "__main__":
    unittest.main()
