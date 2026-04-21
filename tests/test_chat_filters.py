# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""Tests for imperal_sdk.chat.filters — output filter pipeline.

Current coverage:
- normalize_markdown (v1.5.17, Layer 2 markdown hygiene)
"""
from __future__ import annotations

import pytest

from imperal_sdk.chat.filters import normalize_markdown


class TestNormalizeMarkdown:
    """Regression guards for `normalize_markdown` (v1.5.17).

    The function fixes `** text **` → `**text**` glitches emitted by LLMs
    that violate CommonMark's rule that emphasis runs must not have
    leading/trailing whitespace inside the delimiters.
    """

    def test_leading_and_trailing_space_trimmed(self):
        assert normalize_markdown("Hello ** world **!") == "Hello **world**!"

    def test_leading_space_only(self):
        assert normalize_markdown("** text**") == "**text**"

    def test_trailing_space_only(self):
        assert normalize_markdown("**text **") == "**text**"

    def test_empty_bold_collapses_to_empty_string(self):
        assert normalize_markdown("before ** ** after") == "before  after"

    def test_empty_tight_bold_removed(self):
        assert normalize_markdown("**  **") == ""

    def test_internal_spaces_preserved(self):
        # Only leading/trailing whitespace inside ** markers is trimmed —
        # spaces between words are part of the content.
        assert normalize_markdown("**a b c**") == "**a b c**"

    def test_no_change_when_already_clean(self):
        assert normalize_markdown("**ID:** `abc-123`") == "**ID:** `abc-123`"

    def test_idempotent(self):
        s = "** foo ** bar ** baz **"
        once = normalize_markdown(s)
        twice = normalize_markdown(once)
        assert once == twice

    def test_empty_string(self):
        assert normalize_markdown("") == ""

    def test_none_safe(self):
        # None is a valid no-op per the `if not text` guard.
        assert normalize_markdown(None) is None

    def test_text_without_bold_passes_through(self):
        # Fast-path skip when no `**` in text.
        s = "Plain paragraph with no emphasis markers."
        assert normalize_markdown(s) is s

    def test_multiple_bolds_in_one_line(self):
        assert (
            normalize_markdown("** a ** and ** b **")
            == "**a** and **b**"
        )

    def test_bold_across_lines_not_merged(self):
        # Regex uses [^*\n] — a `**` on one line cannot pair with a `**`
        # on the next line. Prevents accidentally swallowing paragraphs.
        s = "**foo\n**bar **baz**"
        # No cross-line match: the first `**foo\n**bar` pair is skipped;
        # only `**baz**` is eligible. Output must preserve the newline.
        assert "\n" in normalize_markdown(s)
        assert "**baz**" in normalize_markdown(s)

    def test_cyrillic_content(self):
        assert (
            normalize_markdown("** Рекомендации **: держите пароли в порядке")
            == "**Рекомендации**: держите пароли в порядке"
        )

    def test_real_world_table_row_unchanged(self):
        row = "| **Домен** | webhostmost.com | OK |"
        assert normalize_markdown(row) == row

    def test_nested_asterisks_not_unwrapped(self):
        # Regex [^*\n] — no embedded `*` inside the match — so `***` or
        # runs containing `*` are left alone rather than mangled.
        s = "*** triple ***"
        out = normalize_markdown(s)
        # Non-matching → passed through. Specific shape is implementation-
        # defined; assertion is: not crashed, no content lost.
        assert "triple" in out


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("** X**", "**X**"),
        ("**X **", "**X**"),
        ("** X **", "**X**"),
        ("**X**", "**X**"),
    ],
)
def test_normalize_markdown_parametrized(raw: str, expected: str):
    assert normalize_markdown(raw) == expected
