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
    kept: int        # characters shown
    total: int       # characters of the whole (masked) output
    ref: str         # whole_ref of the whole copy

    def to_dict(self) -> dict:
        return {"kept": self.kept, "total": self.total, "ref": self.ref}


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
                   cut=Cut(int(cut["kept"]), int(cut["total"]), str(cut["ref"])) if cut else None,
                   masked=tuple(Masked.from_dict(m) for m in d.get("masked") or ()),
                   event_id=str(d.get("event_id") or ""), seq=int(d.get("seq") or 0))


_SPACE = re.compile(r"\s+")


def subject_of(kind: str, target: str) -> str:
    """The one identity of what a record is about: the tool and its target, whitespace-normalised."""
    return f"{str(kind or '').strip().lower()}:{_SPACE.sub(' ', str(target or '')).strip()}"


def _view(text: str, limit: int) -> str:
    """A bounded view of a whole output: its head and its tail, the cut marked inside it."""
    if limit <= 0 or len(text) <= limit:
        return text
    marker = f"\n… [{len(text) - limit} of {len(text)} chars not shown here; the whole is kept] …\n"
    room = max(0, limit - len(marker))
    head = room * 2 // 3
    return text[:head] + marker + text[len(text) - (room - head):] if room - head > 0 else text[:head] + marker


def make_evidence(kind: str, target: str, raw_text: str, provenance: Provenance, exit_code: int | None = None,
                  limit: int = 0, event_id: str = "", code: bool = False) -> tuple:
    """``(record, whole_masked_text)``: the output masked once, its whole copy addressed, and -- the one place an
    output is ever cut -- a view of at most ``limit`` characters with the cut written on the record (0: no cut).
    The caller stores the whole copy under ``record.whole_ref``."""
    whole, masked = mask(str(raw_text or ""), code=code)
    ref = hashlib.sha256(whole.encode("utf-8", "replace")).hexdigest()
    shown = _view(whole, int(limit or 0))
    cut = Cut(kept=len(shown), total=len(whole), ref=ref) if shown != whole else None
    rec = Evidence(kind=str(kind), target=str(target or ""), text=shown, provenance=Provenance(provenance),
                   whole_ref=ref, subject=subject_of(kind, target), exit_code=exit_code, cut=cut,
                   masked=tuple(masked), event_id=str(event_id or ""))
    return rec, whole
