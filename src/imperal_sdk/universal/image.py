"""Images as metadata only (the picture is never decoded): when it was taken, the camera, whether it carries a GPS
position. Read from the Exif block (JPEG APP1, HEIC/PNG ``Exif`` box, a TIFF file itself) by its byte layout."""
from __future__ import annotations

import os
import struct

from imperal_sdk.universal.view import View, register

_SCAN_BYTES = 262_144          # where an Exif block can start in a JPEG / HEIC / PNG header area
_TAGS = {0x010F: "camera_make", 0x0110: "camera_model", 0x0132: "modified", 0x9003: "taken"}


def _tiff_meta(t: bytes) -> dict:
    if len(t) < 8 or t[:2] not in (b"II", b"MM"):
        return {}
    e = "<" if t[:2] == b"II" else ">"

    def ifd(off: int) -> list[tuple[int, int, int, int]]:
        if off + 2 > len(t):
            return []
        n = struct.unpack(e + "H", t[off:off + 2])[0]
        out = []
        for i in range(min(n, 512)):
            p = off + 2 + 12 * i
            if p + 12 > len(t):
                break
            tag, typ, count, value = struct.unpack(e + "HHII", t[p:p + 12])
            out.append((tag, typ, count, value if count * {2: 1, 3: 2, 4: 4}.get(typ, 4) > 4 else p + 8))
        return out

    def ascii_at(typ: int, count: int, off: int) -> str:
        if typ != 2 or off + count > len(t):
            return ""
        return t[off:off + count].split(b"\x00", 1)[0].decode("ascii", "replace").strip()
    meta: dict = {}
    first = struct.unpack(e + "I", t[4:8])[0]
    entries = ifd(first)
    sub = []
    for tag, typ, count, off in entries:
        if tag == 0x8769 and typ == 4 and off + 4 <= len(t):
            # a LONG fits the entry, so ``off`` is where the value lies: the Exif sub-IFD's offset is read there
            sub = ifd(struct.unpack(e + "I", t[off:off + 4])[0])
        if tag == 0x8825:
            meta["gps"] = True
    for tag, typ, count, off in entries + sub:
        if tag in _TAGS:
            val = ascii_at(typ, count, off)
            if val:
                meta[_TAGS[tag]] = val
    return meta


def _image(rel: str, raw: bytes) -> View:
    ext = os.path.splitext(rel.lower())[1]
    if ext in (".tif", ".tiff"):
        meta = _tiff_meta(raw)
    else:
        at = raw.find(b"Exif\x00\x00", 0, _SCAN_BYTES)
        meta = _tiff_meta(raw[at + 6:]) if at >= 0 else {}
    meta["bytes"] = len(raw)
    return View("image", "", meta=meta)


register((".jpg", ".jpeg", ".png", ".heic", ".tif", ".tiff"), _image)
