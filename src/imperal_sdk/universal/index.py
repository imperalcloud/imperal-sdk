"""Views in the code index: a file of any kind read from disk inside its cap, and its view as a ``FileIndex``
(a section is a ``Symbol``, a link a ref) so search, outline and the graph take it as they take code."""
from __future__ import annotations

import hashlib
import os
import stat as _stat

from imperal_sdk.code_index import FileIndex, Symbol
from imperal_sdk.universal.kinds import kind_of, never_read_at
from imperal_sdk.universal.view import View, view_of

# code and configs are parsed whole: the parser holds ~100-300x the file in memory (measured 2026-11-04: a 10 MB .sql
# peaked at 0.98 GB, a 1.4 MB .py at 0.47 GB) -- 1 MB keeps one file under ~0.3 GB; a bigger one (a dump, generated
# code) is listed as skipped with the reason
RAW_CAP = {"code": 1024 * 1024, "config": 1024 * 1024, "document": 100 * 1024 * 1024,
           "data": 100 * 1024 * 1024, "mail": 100 * 1024 * 1024, "image": 100 * 1024 * 1024}
_SF_DATALESS = 0x40000000      # macOS: an iCloud file whose bytes are not on this Mac (reading downloads it)
# Windows: a cloud file (OneDrive, Dropbox, iCloud for Windows) whose bytes are not local -- reading it downloads it
# (final review 2026-11-04): FILE_ATTRIBUTE_OFFLINE | RECALL_ON_OPEN | RECALL_ON_DATA_ACCESS
_WIN_NOT_LOCAL = 0x1000 | 0x40000 | 0x400000


def is_placeholder(rel: str, st: os.stat_result | None = None) -> bool:
    """A cloud placeholder (iCloud on macOS, OneDrive and other cloud files on Windows): never read -- opening it
    starts a download. ``os.stat`` itself never downloads."""
    if rel.endswith(".icloud"):
        return True
    if st is None:
        return False
    return bool(getattr(st, "st_flags", 0) & _SF_DATALESS or getattr(st, "st_file_attributes", 0) & _WIN_NOT_LOCAL)


def readable_file(st: os.stat_result) -> bool:
    """A regular file: a FIFO, a socket or a device never opens (reading a FIFO waits forever -- a hung build)."""
    return _stat.S_ISREG(st.st_mode)


def read_view(root: str, rel: str) -> View | None:
    """The view of ``rel`` under ``root``: None when the index never reads it; ``skipped`` (unread) for a placeholder,
    a file over its kind's cap, a path leaving the root, or one that cannot be opened."""
    if is_placeholder(rel):
        return View("document", "", skipped="placeholder")
    kind = kind_of(rel)
    if kind is None:
        return None
    base = os.path.realpath(root)
    path = os.path.join(base, rel)
    real = os.path.realpath(path)
    if os.path.isabs(rel) or os.path.islink(path) or os.path.commonpath([base, real]) != base:
        return View(kind, "", skipped="outside the folder")
    if never_read_at(base, rel):
        return None                        # a secret store by its real path: the root itself, or where a link leads
    try:
        st = os.stat(real)
    except OSError:
        return View(kind, "", skipped="cannot be opened")
    if not readable_file(st):
        return View(kind, "", skipped="not a regular file")
    if is_placeholder(rel, st):
        return View(kind, "", skipped="placeholder")
    cap = RAW_CAP.get(kind, RAW_CAP["document"])
    if st.st_size > cap:
        return View(kind, "", skipped=f"over {cap // 1048576} MB")
    try:
        with open(real, "rb") as f:
            raw = f.read(cap + 1)
    except OSError:
        return View(kind, "", skipped="cannot be opened")
    return view_of(rel, raw)


def parse_view(rel: str, view: View) -> FileIndex:
    """A view as the code index's ``FileIndex``: sections -> symbols, links -> refs, the view's kind."""
    return FileIndex(
        path=rel, lang="other", kind=view.kind,
        symbols=[Symbol(name=s.title, kind=s.kind, path=rel, start_line=s.start_line, end_line=s.end_line,
                        signature=s.title) for s in view.sections],
        refs=list(view.links),
        content_hash=hashlib.sha256(view.text.encode("utf-8", "replace")).hexdigest())
