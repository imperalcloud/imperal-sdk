"""Evidence: the one record of what an agent saw, and the one set of verdicts on what it said (ICNLI §7.2, §7.3, §7.7).

Until 6.7.0 every stage kept its own cut copy of an output (600 / 1200 / 1600 / 2400 chars, a bag of words for a
withheld command) and no stage knew what an earlier one had dropped -- so a true answer was "not shown". Now:

- an output is recorded ONCE, whole and masked (``secret_mask``), addressed by ``whole_ref`` (its SHA-256);
- what a frame shows is a view of it, and the cut is written on the record (``Cut``), so every reader knows;
- every record says where it came from (``Provenance``): run by the agent, measured by a hook, shown by the kernel,
  given by the user, recalled from memory, written by the agent itself, or a shell's notification;
- ``subject`` is the one identity of "what it is about" (the newest record about a subject wins, never word overlap);
- six verdicts, two of them blocking: a contradiction quoted verbatim, or "checked" said where nothing ran.

Judging a record (what a command did, whether an empty search is a fact of absence) is the kernel's: it owns
the command parser (``action_effect.command_lines``, ``plan_contract.program_of``).
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from enum import Enum

from imperal_sdk.code_index import line_count
from imperal_sdk.secret_mask import Masked, mask


class Provenance(str, Enum):
    EXECUTED = "executed"          # a tool the agent ran
    MEASURED = "measured"          # a hook's own measure (HEAD, cwd)
    FRAME = "frame"                # what the kernel itself showed the agent
    USER = "user"                  # the user's words: the prompt and anything pasted into it
    MEMORY = "memory"              # recalled: memory, an earlier session
    OWN_WRITE = "own_write"        # a file the agent wrote
    NOTIFICATION = "notification"  # the shell's own notice (a background task finished)


class Verdict(str, Enum):
    SHOWN = "shown"                        # a record supports the claim
    CONTRADICTED = "contradicted"          # the newest record about the subject says otherwise, quoted verbatim
    STATED_UNPROVEN = "stated_unproven"    # "checked / passed / done" said, and nothing about it ran
    FROM_SOURCE = "from_source"            # rests on the user's words, memory or the frame -- and that source is held
    KERNEL_BLIND = "kernel_blind"          # the record that would decide it was cut or masked
    NOT_SHOWN = "not_shown"                # no support found, and nothing was claimed as checked


# ICNLI §7.7: the judge is contractual, never structural -- only verdicts resting on held records block an answer
BLOCKING = frozenset({Verdict.CONTRADICTED, Verdict.STATED_UNPROVEN})


@dataclass(frozen=True)
class Cut:
    kept: int               # characters shown
    total: int              # characters of the whole (masked) output
    ref: str                # whole_ref of the whole copy
    kept_lines: int = 0     # whole lines shown (``code_index.line_count`` of the shown parts)
    total_lines: int = 0    # lines of the whole
    address: str = ""       # how a reader opens the whole: a call or a path, as the cut's own marker says it

    def to_dict(self) -> dict:
        return {"kept": self.kept, "total": self.total, "ref": self.ref, "kept_lines": self.kept_lines,
                "total_lines": self.total_lines, "address": self.address}

    @classmethod
    def from_dict(cls, d: dict) -> "Cut":
        """Reads a cut written before 6.8.0 too (characters and ref only)."""
        return cls(kept=int(d["kept"]), total=int(d["total"]), ref=str(d.get("ref") or ""),
                   kept_lines=int(d.get("kept_lines") or 0), total_lines=int(d.get("total_lines") or 0),
                   address=str(d.get("address") or ""))


@dataclass(frozen=True)
class Evidence:
    kind: str                       # the tool's name, or prompt / frame / measure / notification
    target: str                     # the command, path, URL or query
    text: str                       # what a reader sees (masked; cut when ``cut`` is set)
    provenance: Provenance
    whole_ref: str                  # SHA-256 of the whole masked output
    subject: str                    # subject_of(kind, target)
    exit_code: int | None = None
    cut: Cut | None = None
    masked: tuple = field(default_factory=tuple)      # tuple[Masked, ...]
    event_id: str = ""              # the client's id of the event (idempotency)
    seq: int = 0                    # the session log's sequence number (0 until appended)

    def to_dict(self) -> dict:
        return {"kind": self.kind, "target": self.target, "text": self.text, "provenance": self.provenance.value,
                "whole_ref": self.whole_ref, "subject": self.subject, "exit_code": self.exit_code,
                "cut": self.cut.to_dict() if self.cut else None, "masked": [m.to_dict() for m in self.masked],
                "event_id": self.event_id, "seq": self.seq}

    @classmethod
    def from_dict(cls, d: dict) -> "Evidence":
        cut = d.get("cut")
        return cls(kind=str(d["kind"]), target=str(d.get("target") or ""), text=str(d.get("text") or ""),
                   provenance=Provenance(d["provenance"]), whole_ref=str(d["whole_ref"]),
                   subject=str(d.get("subject") or ""),
                   exit_code=None if d.get("exit_code") is None else int(d["exit_code"]),
                   cut=Cut.from_dict(cut) if cut else None,
                   masked=tuple(Masked.from_dict(m) for m in d.get("masked") or ()),
                   event_id=str(d.get("event_id") or ""), seq=int(d.get("seq") or 0))


_SPACE = re.compile(r"\s+")


def subject_of(kind: str, target: str) -> str:
    """The one identity of what a record is about: the tool and its target, whitespace-normalised."""
    return f"{str(kind or '').strip().lower()}:{_SPACE.sub(' ', str(target or '')).strip()}"


def _whole_lines(head: str, tail: str) -> tuple:
    """The head up to its last line break and the tail from its first: a view shows whole lines wherever the text
    has them (one line longer than its part is shown as far as it goes)."""
    at = head.rfind("\n")
    if at >= 0:
        head = head[:at + 1]
    at = tail.find("\n")
    if 0 <= at < len(tail) - 1:
        tail = tail[at + 1:]
    return head, tail


def cut_marker(missing: int, total: int, where: str, missing_lines: int | None = None,
               total_lines: int | None = None) -> str:
    """The one wording of "a part is not shown": how many characters (and lines, when the whole was counted) are
    missing and where the whole is. ``cut_text`` writes it; a reader that holds only parts of a whole it never
    loaded (a window of a log) writes the same line with it."""
    lines = f" ({missing_lines} of {total_lines} lines)" if missing_lines is not None and total_lines is not None else ""
    return f"\n… [{missing} of {total} chars{lines} not shown here; the whole: {where}] …\n"


def cut_text(text: str, limit: int, ref: str = "", address: str = "") -> tuple:
    """``(shown, cut)`` -- the ONE place a text is cut (ICNLI §7.2; until 6.8.0 only tool outputs came here and the
    kernel kept about twenty cutters of its own, most of them leaving a bare "…"). At most ``limit`` characters of
    ``text``: its head and its tail in whole lines, and between them a marker that says how much is not shown --
    characters and lines -- and where the whole is (``address``: the call or the path a reader opens it by; without
    one, the whole copy's ``ref``). ``cut`` is None when nothing was cut (``limit`` 0, or the text fits)."""
    text = str(text or "")
    limit = int(limit or 0)
    if limit <= 0 or len(text) <= limit:
        return text, None
    total_lines = line_count(text)
    where = str(address or "").strip() or (f"kept whole, ref {ref[:12]}" if ref else "not kept")

    def marker(chars: int, lines: int) -> str:
        return cut_marker(chars, len(text), where, lines, total_lines)
    room = max(0, limit - len(marker(len(text), total_lines)))
    head_room = room * 2 // 3
    head, tail = _whole_lines(text[:head_room], text[len(text) - (room - head_room):] if room > head_room else "")
    kept_lines = line_count(head) + line_count(tail)
    shown = head + marker(len(text) - len(head) - len(tail), max(0, total_lines - kept_lines)) + tail
    return shown, Cut(kept=len(shown), total=len(text), ref=str(ref or ""), kept_lines=kept_lines,
                      total_lines=total_lines, address=str(address or "").strip())


def make_evidence(kind: str, target: str, raw_text: str, provenance: Provenance, exit_code: int | None = None,
                  limit: int = 0, event_id: str = "", code: bool = False, address: str = "") -> tuple:
    """``(record, whole_masked_text)``: the output masked once, its whole copy addressed, and a view of at most
    ``limit`` characters (``cut_text``) with the cut written on the record (0: no cut). ``address``: how a reader
    opens the whole copy, said in the view's own marker. The caller stores the whole copy under
    ``record.whole_ref``."""
    whole, masked = mask(str(raw_text or ""), code=code)
    ref = hashlib.sha256(whole.encode("utf-8", "replace")).hexdigest()
    shown, cut = cut_text(whole, int(limit or 0), ref=ref, address=address)
    rec = Evidence(kind=str(kind), target=str(target or ""), text=shown, provenance=Provenance(provenance),
                   whole_ref=ref, subject=subject_of(kind, target), exit_code=exit_code, cut=cut,
                   masked=tuple(masked), event_id=str(event_id or ""))
    return rec, whole
