"""What a file is (code, config, document, data, mail, image) and what is never read, whatever it is.

One table for every source that lists files for the universal index. It never widens what reaches the vault:
``code_index.indexable`` stays that filter (the vault carries a literal copy of it).
"""
from __future__ import annotations

import fnmatch
import os

from imperal_sdk.code_index import _DRIVE, _TSCONFIG, CONFIG_NAMES, SECRET_PATTERNS, SKIP_DIRS, _slashes

# extension -> the tree-sitter language name (tree-sitter-language-pack's names)
CODE_LANGS: dict[str, str] = {
    ".py": "python", ".pyi": "python", ".ts": "typescript", ".tsx": "tsx", ".js": "javascript",
    ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript", ".kt": "kotlin", ".kts": "kotlin",
    ".java": "java", ".swift": "swift", ".go": "go", ".rs": "rust", ".c": "c", ".h": "c", ".cc": "cpp",
    ".cpp": "cpp", ".hpp": "cpp", ".cs": "csharp", ".php": "php", ".rb": "ruby", ".dart": "dart",
    ".scala": "scala", ".lua": "lua", ".sh": "bash", ".bash": "bash", ".zsh": "bash", ".sql": "sql",
    ".html": "html", ".css": "css", ".scss": "scss",
}
DOCUMENT_EXT = frozenset({".docx", ".doc", ".odt", ".rtf", ".pdf", ".pptx", ".ppt", ".odp", ".txt", ".md",
                          ".markdown", ".rst", ".htm"})
DATA_EXT = frozenset({".xlsx", ".xls", ".ods", ".csv", ".tsv", ".json", ".yaml", ".yml", ".toml", ".xml"})
MAIL_EXT = frozenset({".eml", ".mbox"})
IMAGE_EXT = frozenset({".jpg", ".jpeg", ".png", ".heic", ".tif", ".tiff"})

# never read, whatever the kind: the parent list plus a person's keys, keychains, VPN profiles, wallets and browsers
_NEVER_NAMES = SECRET_PATTERNS + ("*.keychain", "*.keychain-db", "*.ovpn", "*.mobileconfig", "wallet.dat", "*.kdb")
_NEVER_PATHS = (".gnupg/", "Library/Keychains/", "Library/Application Support/Google/Chrome/",
                "Library/Application Support/Firefox/Profiles/", "Library/Application Support/BraveSoftware/",
                "Library/Application Support/Microsoft Edge/", "Library/Safari/", "Library/Cookies/",
                ".mozilla/", ".password-store/")
# iCloud Drive lives under Library: it is a person's files, the rest of Library is not
_ICLOUD = "Library/Mobile Documents/"


def _parts(rel_path: str) -> list[str]:
    parts = [x for x in _slashes(rel_path).split("/") if x]
    if parts and _DRIVE.match(parts[0]):
        parts = parts[1:]
    return parts


def never_read(rel_path: str) -> bool:
    """True for a path no extractor may open: secrets by name, and the secret stores of a home folder."""
    parts = _parts(rel_path)
    if not parts:
        return True
    joined = "/".join(parts) + ("/" if len(parts) > 1 else "")
    if any(joined.startswith(p) or f"/{p}" in f"/{joined}" for p in _NEVER_PATHS):
        return True
    for pat in _NEVER_NAMES:
        if pat.endswith("/"):
            if pat[:-1] in parts[:-1]:
                return True
        elif fnmatch.fnmatchcase(parts[-1].lower(), pat):
            return True
    return False


def kind_of(rel_path: str) -> str | None:
    """``code | config | document | data | mail | image``, or None (never read, a dependency / build / cache
    tree, a dotted directory, or no kind the index reads)."""
    if never_read(rel_path):
        return None
    parts = _parts(rel_path)
    in_icloud = "/".join(parts).startswith(_ICLOUD)
    dirs = parts[2:-1] if in_icloud else parts[:-1]
    for d in dirs:
        if d.startswith(".") or d in SKIP_DIRS or d.startswith("Program Files"):
            return None
    name = parts[-1].lower()
    if name in CONFIG_NAMES or _TSCONFIG.match(name):
        return "config"
    ext = os.path.splitext(name)[1]
    if ext in CODE_LANGS:
        return "code"
    if ext in DOCUMENT_EXT:
        return "document"
    if ext in DATA_EXT:
        return "data"
    if ext in MAIL_EXT:
        return "mail"
    if ext in IMAGE_EXT:
        return "image"
    return None
