"""The universal index: every file kind a person works with, read into one graph.

Design: docs/superpowers/specs/2026-11-03-universal-index-design.md (ipw-repo). ``kinds`` says what a file is
and what is never read; ``view`` turns any file into readable text with sections and links.
``code_index.indexable`` stays the filter of what may reach the vault (code and resolution configs only).
"""
