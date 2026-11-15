"""One line count for every tool (field test 2026-11-14 Н3: outline said 133 where `wc -l` said 132)."""
import pytest

from imperal_sdk.code_index import line_count


@pytest.mark.parametrize("text, n", [
    ("", 0),
    ("a", 1),
    ("a\n", 1),
    ("a\nb", 2),
    ("a\r\nb\r\n", 2),
    ("a b\n", 1),          # a Unicode line separator is no line break to wc -l or an editor
    ("a\x0cb\n", 1),
    ("x\n" * 600, 600),
])
def test_line_count_matches_editors(text, n):
    assert line_count(text) == n


def test_view_uses_the_same_count():
    from imperal_sdk.universal import view
    assert view.line_count is line_count
