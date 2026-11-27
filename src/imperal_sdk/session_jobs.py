# Copyright (c) 2026 Imperal, Inc.
# Licensed under the AGPL-3.0 License.
"""A job of a session ON ITS MACHINE: the folder, the three shell lines and the reading of a poll.

A long command runs as a job: started detached in its own process group, its output in a log, its exit code in a
file. Whoever reaches the machine reads it by one read-only line -- the kernel over SSH for a machine of the
account, the person's own client for the machine it runs on (one-loop plan 2026-11-26, rule 8: "a child process
that works the way yours does"). The format has ONE owner, here: the kernel writes the lines and reads the poll, the
client runs the same lines -- no copy of a shell line anywhere else. Everything in this module is pure.

On the machine: ``$HOME/.imperal-jobs/<session>-<n>/{log,exit,pid,cancel}``."""
from __future__ import annotations

import re
import shlex
from typing import Any, Dict

from imperal_sdk.evidence import cut_text

JOB_ROOT = "$HOME/.imperal-jobs"       # on the job's machine: <root>/<dir>/{log,exit,pid,cancel}
TAIL_CHARS = 2000                      # the end of the log a poll reads and a report shows

RUNNING, DONE, FAILED, CANCELLED, LOST = "running", "done", "failed", "cancelled", "lost"
ENDED = frozenset({DONE, FAILED, CANCELLED, LOST})
# The watch is bounded by the job's own end, never by a timer (owner 2026-11-19: an outcome by fact). These two only
# pace the reading: quick while a job that fails at once would fail, then calm (measured 2026-11-25: the kernel's
# full suite runs 1990 s -- 30 s between polls is 66 short reads of it).
POLL_FIRST_S, POLL_S, POLLS_FIRST = 5, 30, 12
_MARK = "---imperal-job---"
_SAFE = re.compile(r"[^A-Za-z0-9_.-]")
_DIR = re.compile(r"\$HOME/\.imperal-jobs/[A-Za-z0-9_.-]+")


def _dir(directory: str) -> str:
    """PURE. The folder as a shell line may hold it: exactly the form ``job_dir`` gives (``$HOME`` is expanded by the
    machine's shell, so the word cannot be quoted -- it is checked instead). Anything else is refused: a folder read
    back from a record is data, and data is never pasted into a command (review k13 part 1: a folder holding
    ``; touch x`` ran it)."""
    if not _DIR.fullmatch(str(directory or "")):
        raise ValueError("not a job folder of the kernel's own form")
    return str(directory)


def job_id(n: int) -> str:
    return f"j{int(n)}"


def job_dir(session_id: str, n: int) -> str:
    """PURE. The job's folder on its machine; the session's id whole, reduced to file-safe characters (a session id
    is at most 200 characters -- workflows.agent_messages._SESSION_ID)."""
    return f"{JOB_ROOT}/{_SAFE.sub('_', str(session_id))}-{int(n)}"


def start_line(command: str, directory: str) -> str:
    """PURE. The shell line that starts ``command`` detached in its own process group: output to the job's log, exit
    code to its exit file, the group's id to its pid file. The line returns at once and the command runs where a
    command on that machine starts (its own ``cd`` is its own). The command is passed as ONE quoted word to
    ``sh -c`` -- nothing of it is read by the line itself."""
    directory = _dir(directory)
    inner = f"sh -c {shlex.quote(str(command))}; echo $? > {directory}/exit"
    q = shlex.quote(inner)
    return (f"mkdir -p {directory} && rm -f {directory}/exit {directory}/cancel && "
            # its own process group either way: setsid where the machine has it, else the shell's job control
            # (measured 2026-11-25: macOS has no setsid -- the job died at once and read as "lost")
            f"(if command -v setsid >/dev/null 2>&1; then setsid nohup sh -c {q} > {directory}/log 2>&1 < /dev/null & "
            f"else set -m; nohup sh -c {q} > {directory}/log 2>&1 < /dev/null & fi; echo $! > {directory}/pid) "
            f"&& echo {_MARK} started $(cat {directory}/pid)")


def poll_line(directory: str) -> str:
    """PURE. The read-only line a poll runs: whether the job's group still lives, the exit code if it wrote one,
    whether it was cancelled, the end of its log. Liveness is read BEFORE the exit file: a job that ends between the
    two reads then shows its code, never "gone without a code" (measured 2026-11-25: a job of a few milliseconds read
    as lost). The group, or the process itself -- in the instant after the start the group is not formed yet. No
    ``--`` before the group: dash's kill does not take it."""
    directory = _dir(directory)
    return (f"cd {directory} 2>/dev/null || {{ echo {_MARK} nodir; exit 0; }}; p=$(cat pid 2>/dev/null); "
            f"a=$({{ kill -0 -$p || kill -0 $p; }} 2>/dev/null && echo 1 || echo 0); "
            f"echo {_MARK} alive=$a exit=$(cat exit 2>/dev/null) cancel=$([ -f cancel ] && echo 1 || echo 0); "
            f"tail -c {TAIL_CHARS} log 2>/dev/null")


def cancel_line(directory: str) -> str:
    """PURE. The line that ends the job: the mark first (the poll then reads "cancelled", not "lost"), then the
    whole process group (the process alone only where no group formed)."""
    directory = _dir(directory)
    return (f"cd {directory} && touch cancel && p=$(cat pid) && {{ kill -TERM -$p 2>/dev/null || kill -TERM $p; }} ; "
            f"echo {_MARK} cancel sent")


def read_poll(stdout: str) -> Dict[str, Any]:
    """PURE. What a poll's output says: ``{state, exit_code, tail}``. A job with an exit code ended by it; one whose
    group is gone without a code was cancelled (its mark is there) or is lost; no folder at all is lost."""
    text = str(stdout or "")
    at = text.find(_MARK)                       # wherever it stands: a login banner before it is the machine's
    if at < 0:                                  # not this line's output: nothing can be said from it
        return {"state": "", "exit_code": None, "tail": ""}
    head, _, tail = text[at:].partition("\n")
    if head.strip().endswith("nodir"):
        return {"state": LOST, "exit_code": None, "tail": ""}
    f = dict(p.split("=", 1) for p in head.split() if "=" in p)
    code = f.get("exit", "")
    tail = cut_text(tail, TAIL_CHARS)[0] if len(tail) > TAIL_CHARS else tail
    if re.fullmatch(r"-?\d+", code or ""):
        if f.get("cancel") == "1":
            return {"state": CANCELLED, "exit_code": int(code), "tail": tail}
        return {"state": DONE if int(code) == 0 else FAILED, "exit_code": int(code), "tail": tail}
    if f.get("alive") == "1":
        return {"state": RUNNING, "exit_code": None, "tail": tail}
    return {"state": CANCELLED if f.get("cancel") == "1" else LOST, "exit_code": None, "tail": tail}


def local_dir(directory: str, home: str) -> str:
    """PURE. The job's folder as a path on the machine itself (``$HOME`` resolved to ``home``) -- for the client
    that looks into its own folders; the shell lines keep the ``$HOME`` form."""
    return str(home).rstrip("/") + _dir(directory)[len("$HOME"):]


def job_of_dir(name: str):
    """PURE. ``(session part, n)`` of a job folder's name (``<session>-<n>``), or None for another name."""
    m = re.fullmatch(r"([A-Za-z0-9_.-]+)-(\d{1,4})", str(name or ""))
    return (m.group(1), int(m.group(2))) if m else None


def session_part(session_id: str) -> str:
    """PURE. The session's id as a job folder's name carries it."""
    return _SAFE.sub("_", str(session_id))
