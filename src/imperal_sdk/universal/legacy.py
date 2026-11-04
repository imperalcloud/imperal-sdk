"""Legacy Office files (``.doc .xls .ppt``) as text. A converter the system already has is used when found
(macOS ``textutil`` for .doc, ``antiword`` / ``catdoc``, ``xls2csv``, ``catppt``), never required; else the text
runs of the OLE streams are read with ``olefile`` (approximate: the words are there, the layout is not)."""
from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import tempfile

from imperal_sdk.universal.view import View, register

CONVERTER_TIMEOUT_S = 30
_OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_STREAMS = {".doc": ("WordDocument",), ".xls": ("Workbook", "Book"), ".ppt": ("PowerPoint Document",)}
_MIN_RUN = 4


def _converter(ext: str) -> list[str] | None:
    """The argv prefix of a converter on this machine that prints the file's text to stdout, or None."""
    if ext == ".doc" and sys.platform == "darwin" and shutil.which("textutil"):
        return ["textutil", "-convert", "txt", "-stdout"]
    for tool, exts in (("antiword", (".doc",)), ("catdoc", (".doc",)), ("xls2csv", (".xls",)), ("catppt", (".ppt",))):
        if ext in exts and shutil.which(tool):
            return [tool]
    return None


def _convert(argv: list[str], raw: bytes, ext: str) -> str | None:
    with tempfile.TemporaryDirectory(prefix="imperal-view-") as d:
        path = os.path.join(d, "file" + ext)
        with open(path, "wb") as f:
            f.write(raw)
        try:
            out = subprocess.run(argv + [path], capture_output=True, timeout=CONVERTER_TIMEOUT_S)
        except (OSError, subprocess.TimeoutExpired):
            return None
    if out.returncode != 0:
        return None
    return out.stdout.decode("utf-8", "replace")


def _runs(data: bytes) -> list[str]:
    """Text runs of a binary stream: UTF-16LE runs and single-byte (cp1252) runs of printable characters."""
    found: list[tuple[int, str]] = []
    for codec, step in (("utf-16-le", 2), ("cp1252", 1)):
        cur, start = [], 0
        for i in range(0, len(data) - step + 1, step):
            ch = data[i:i + step].decode(codec, "ignore")
            if ch and (ch.isprintable() or ch in "\t") and ch != "\x00":
                if not cur:
                    start = i
                cur.append(ch)
            else:
                if len(cur) >= _MIN_RUN:
                    found.append((start, "".join(cur)))
                cur = []
        if len(cur) >= _MIN_RUN:
            found.append((start, "".join(cur)))
    found.sort()
    out: list[str] = []
    for _pos, s in found:
        s = " ".join(s.split())
        if len(s) >= _MIN_RUN and sum(c.isalnum() for c in s) >= len(s) // 2 and s not in out:
            out.append(s)
    return out


def _ole_text(raw: bytes, ext: str) -> str | None:
    try:
        import olefile
    except ImportError:
        return None
    try:
        ole = olefile.OleFileIO(io.BytesIO(raw))
    except Exception:
        return None
    try:
        for name in _STREAMS.get(ext, ()):
            if ole.exists(name):
                return "\n".join(_runs(ole.openstream(name).read()))
    finally:
        ole.close()
    return None


def _legacy(rel: str, raw: bytes) -> View:
    ext = os.path.splitext(rel.lower())[1]
    if not raw.startswith(_OLE):
        return View("document", "", skipped="not a legacy Office file")
    argv = _converter(ext)
    if argv:
        text = _convert(argv, raw, ext)
        if text is not None:
            return View("document", text.strip())
    text = _ole_text(raw, ext)
    if text is None:
        return View("document", "", skipped="no reader for legacy Office (imperal-sdk[universal-index])")
    return View("document", text, meta={"extracted": "approximate"})


register((".doc", ".xls", ".ppt"), _legacy)
