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


def test_credential_files_that_look_like_data_are_never_read():
    """security review 2026-11-04: a service-account key or a password export is JSON or CSV by format."""
    for p in ("gcp/credentials.json", "Downloads/client_secret_123.apps.googleusercontent.com.json",
              "ops/my-project-service-account.json", "token.json", "infra/terraform.tfstate", "prod.tfvars",
              "k8s/kubeconfig.yaml", ".netrc", "home/.pgpass", "Downloads/Chrome Passwords.csv",
              "keys/backup.gpg", "secrets.yaml"):
        assert kind_of(p) is None, p
    assert kind_of("finance/2026-budget.json") == "data" and kind_of("bank/statement.csv") == "data"


def test_build_files_known_by_name_are_code():
    for p in ("Dockerfile", "svc/Dockerfile.prod", "Makefile", "Gemfile", "ci/Jenkinsfile", "Procfile"):
        assert kind_of(p) == "code", p
    from imperal_sdk.code_index import _lang_for
    assert _lang_for("svc/Dockerfile") == "dockerfile" and _lang_for("Makefile") == "make"
    assert _lang_for("a.py") == "python"
