"""Universal index phase 2, Task 2: definitions in every language the grammar pack carries."""
import pytest

from imperal_sdk.code_index import parse_file

pytest.importorskip("tree_sitter_language_pack")

CASES = {"a/Main.kt": ("class Wallet { fun pay(x: Int) = x }", {"Wallet", "pay"}),
         "A.java": ("class Ledger { void post() {} }", {"Ledger", "post"}),
         "m.go": ("package m\nfunc Settle() {}\ntype Book struct{}", {"Settle", "Book"}),
         "l.rs": ("fn audit() {}\nstruct Entry;", {"audit", "Entry"}),
         "V.swift": ("class Vault { func open() {} }", {"Vault", "open"}),
         "P.cs": ("class Pay { void Run() {} }", {"Pay", "Run"}),
         "x.rb": ("class Inv\n def total; end\nend", {"Inv", "total"}),
         "s.php": ("<?php function fee() {} class Tax {}", {"fee", "Tax"})}


@pytest.mark.parametrize("path", sorted(CASES))
def test_definitions_in_every_language(path):
    text, names = CASES[path]
    fi = parse_file(path, text)
    assert names <= {s.name for s in fi.symbols}, (path, [(s.name, s.kind) for s in fi.symbols])
