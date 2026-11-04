"""Universal index phase 2, Task 1: every file kind, and the files never read whatever their kind."""
from imperal_sdk.code_index import indexable
from imperal_sdk.universal.kinds import CODE_LANGS, kind_of, never_read


def test_every_kind():
    assert kind_of("app/Main.kt") == "code" and CODE_LANGS[".kt"] == "kotlin"
    assert kind_of("svc/main.go") == "code" and kind_of("lib.rs") == "code" and kind_of("A.swift") == "code"
    assert kind_of("Contracts/NDA 2026.docx") == "document" and kind_of("old.doc") == "document"
    assert kind_of("scan.pdf") == "document" and kind_of("deck.pptx") == "document"
    assert kind_of("ledger.xlsx") == "data" and kind_of("bank.csv") == "data" and kind_of("a.yaml") == "data"
    assert kind_of("inbox/msg.eml") == "mail" and kind_of("photo.HEIC") == "image"
    assert kind_of("tsconfig.json") == "config"


def test_never_read_beats_every_kind():
    for p in (".env", "keys/id_rsa", ".gnupg/notes.docx", "Library/Keychains/login.keychain-db",
              "vpn/office.ovpn", "Library/Application Support/Google/Chrome/Default/History"):
        assert never_read(p) and kind_of(p) is None, p
    assert kind_of("Library/Mobile Documents/com~apple~CloudDocs/report.docx") == "document"
    assert kind_of("Library/Caches/x.pdf") is None and kind_of("node_modules/a/b.js") is None


def test_the_vault_filter_is_unchanged():
    assert indexable("Contracts/NDA.docx") is None and indexable("app/main.py") == "code"
