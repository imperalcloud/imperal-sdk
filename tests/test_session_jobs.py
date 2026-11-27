"""imperal_sdk.session_jobs: a job of a session on its machine -- one owner of the format (rule 8, 2026-11-27).

The lines are run for real here, in a throwaway HOME: the job is started detached, outlives the shell that started
it, and its end is read by the poll line -- the same three lines the kernel runs over SSH and the client runs on
its own machine."""
import os
import subprocess
import time

import pytest

from imperal_sdk import session_jobs as sj

SID = "marathon-imp_u_x-r8ff-s1"


def _sh(line, home):
    return subprocess.run(["sh", "-c", line], capture_output=True, text=True, timeout=30,
                          env={"HOME": str(home), "PATH": os.environ.get("PATH", "/usr/bin:/bin")})


def _wait(home, directory, until, seconds=15.0):
    t = time.time()
    while time.time() - t < seconds:
        got = sj.read_poll(_sh(sj.poll_line(directory), home).stdout)
        if got["state"] in until:
            return got
        time.sleep(0.2)
    return got


def test_the_folder_is_the_kernels_own_form_and_nothing_else_enters_a_line():
    d = sj.job_dir(SID, 7)
    assert d == "$HOME/.imperal-jobs/marathon-imp_u_x-r8ff-s1-7" and sj.job_id(7) == "j7"
    assert sj.job_dir("a/b c;rm", 1) == "$HOME/.imperal-jobs/a_b_c_rm-1"
    for odd in ("", "..", "x-", "trailing.", "-"):                       # every id gives a folder its own lines take
        assert sj.poll_line(sj.job_dir(odd, 3)) and sj.job_of_dir(sj.job_dir(odd, 3).rsplit("/", 1)[1]) == (sj.session_part(odd), 3)
    for bad in ("$HOME/.imperal-jobs/x; touch y", "/tmp/x", "$HOME/.imperal-jobs/../x", "", "$HOME/.imperal-jobs/..",
                "$HOME/.imperal-jobs/.", "$HOME/.imperal-jobs/notes", "$HOME/.imperal-jobs/..-1",
                "$HOME/.imperal-jobs/x-12345"):
        with pytest.raises(ValueError):
            sj.poll_line(bad)
        with pytest.raises(ValueError):
            sj.start_line("true", bad)
        with pytest.raises(ValueError):
            sj.cancel_line(bad)
    assert sj.local_dir(d, "/home/u") == "/home/u/.imperal-jobs/marathon-imp_u_x-r8ff-s1-7"
    assert sj.job_of_dir("marathon-imp_u_x-r8ff-s1-7") == (sj.session_part(SID), 7)
    assert sj.job_of_dir("notes") is None and sj.job_of_dir("x-0007") == ("x", 7)


def test_a_job_outlives_the_shell_that_started_it_and_its_end_is_read(tmp_path):
    d = sj.job_dir(SID, 1)
    started = _sh(sj.start_line("sleep 1; echo hello; exit 3", d), tmp_path)
    assert "started" in started.stdout                     # the starting shell has already returned
    assert _wait(tmp_path, d, {sj.RUNNING}, 3.0)["state"] == sj.RUNNING
    got = _wait(tmp_path, d, sj.ENDED)
    assert got == {"state": sj.FAILED, "exit_code": 3, "tail": "hello\n"}
    ok = sj.job_dir(SID, 2)
    _sh(sj.start_line("echo done", ok), tmp_path)
    assert _wait(tmp_path, ok, sj.ENDED)["state"] == sj.DONE
    assert os.path.exists(os.path.join(sj.local_dir(ok, str(tmp_path)), "exit"))


def test_a_cancelled_job_reads_as_cancelled_and_a_missing_folder_as_lost(tmp_path):
    d = sj.job_dir(SID, 3)
    _sh(sj.start_line("sleep 60", d), tmp_path)
    assert _wait(tmp_path, d, {sj.RUNNING}, 3.0)["state"] == sj.RUNNING
    assert "cancel sent" in _sh(sj.cancel_line(d), tmp_path).stdout
    assert _wait(tmp_path, d, sj.ENDED)["state"] == sj.CANCELLED
    assert sj.read_poll(_sh(sj.poll_line(sj.job_dir(SID, 99)), tmp_path).stdout)["state"] == sj.LOST
    assert sj.read_poll("a banner\nnothing of ours") == {"state": "", "exit_code": None, "tail": ""}
