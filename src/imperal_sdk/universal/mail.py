"""Mail as a view: a message's headers and its text, its attachments as links; an mbox as one ``message`` section
per message. Standard library only."""
from __future__ import annotations

from email import policy
from email.parser import BytesParser

from imperal_sdk.universal.view import View, close_sections, line_count, register

MBOX_MAX_MESSAGES = 10_000


def _body(msg) -> str:
    try:
        part = msg.get_body(preferencelist=("plain", "html"))
    except Exception:
        part = None
    if part is None:
        return ""
    try:
        content = part.get_content()
    except Exception:
        return ""
    if part.get_content_subtype() == "html":
        from imperal_sdk.universal.textual import _html
        return _html("m.html", str(content).encode("utf-8")).text
    return str(content)


def _render(msg) -> tuple[list[str], dict, list[str]]:
    meta = {k: str(msg.get(k) or "") for k in ("from", "to", "subject", "date")}
    att = [p.get_filename() for p in msg.iter_attachments() if p.get_filename()]
    lines = [f"From: {meta['from']}", f"To: {meta['to']}", f"Date: {meta['date']}", f"Subject: {meta['subject']}", ""]
    lines += [ln.rstrip() for ln in _body(msg).splitlines()]
    if att:
        lines.append("Attachments: " + ", ".join(att))
    return lines, meta, att


def _eml(rel: str, raw: bytes) -> View:
    msg = BytesParser(policy=policy.default).parsebytes(raw)
    lines, meta, att = _render(msg)
    text = "\n".join(lines)
    head = [(meta["subject"] or "(no subject)", "message", 1, 1)]
    return View("mail", text, close_sections(head, line_count(text)), att, meta=meta)


def _mbox(rel: str, raw: bytes) -> View:
    chunks: list[bytes] = []
    cur: list[bytes] = []
    for line in raw.splitlines(keepends=True):
        if line.startswith(b"From ") and cur:
            chunks.append(b"".join(cur))
            cur = []
        if line.startswith(b"From ") and not cur:
            continue                       # the mbox separator line itself
        cur.append(line)
    if cur:
        chunks.append(b"".join(cur))
    lines: list[str] = []
    heads = []
    links: list[str] = []
    for chunk in chunks[:MBOX_MAX_MESSAGES]:
        msg = BytesParser(policy=policy.default).parsebytes(chunk)
        body, meta, att = _render(msg)
        heads.append((f"{meta['date']} - {meta['subject'] or '(no subject)'}", "message", 1, len(lines) + 1))
        lines += body + [""]
        links += att
    text = "\n".join(lines)
    return View("mail", text, close_sections(heads, line_count(text)), list(dict.fromkeys(links)),
                meta={"messages": len(chunks)})


register((".eml",), _eml)
register((".mbox",), _mbox)
