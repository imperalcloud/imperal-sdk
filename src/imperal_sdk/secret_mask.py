"""Secret masking: the one owner of what is secret -- in a text (masked) and as a file (its content is secret).

Until 6.7.0 two copies lived apart and drifted: the kernel's ``core/repo_memory.scrub_secrets`` and imperal-mcp's
``secrets_scrub`` ("verbatim port, keep IN SYNC") -- each had rules the other lacked. This module is their union; the
kernel, the gateway, imperal-mcp and webbee import it. ICNLI §7.5: the model sees the mask; the fact ledger keeps
where the mask stands and the value's length -- never the value, nor a hash of it -- so the rest of an output stays
evidence (§7.2) instead of being withheld whole.

A file is secret by its NAME (``.env``, keys, certificates); the index's skip list (``code_index.SKIP_PATTERNS``) is a
separate thing: ``.git/`` is skipped by the index but nothing in it is a secret by name.
"""
from __future__ import annotations

import fnmatch
import functools
import math
import re
from dataclasses import dataclass

# files whose CONTENT is secret: never read into an index, an answer or a fact -- keys and certificates, a person's
# keychains, VPN profiles and wallets, and credential files that look like plain data (security review 2026-11-04:
# cloud keys, tokens, infra state, tool logins, browser password exports)
SECRET_FILES = (".env*", "*.pem", "*.key", "*.crt", "id_*", "*.p12", "*.pfx", "*.kdbx", "secrets/", ".ssh/", ".aws/",
                "*.keychain", "*.keychain-db", "*.ovpn", "*.mobileconfig", "wallet.dat", "*.kdb",
                "credentials*", "*credentials.json", "client_secret*.json", "*service-account*.json",
                "*service_account*.json", "token.json", "tokens.json", "secrets.*", "*kubeconfig*", "*.tfstate",
                "*.tfstate.*", "*.tfvars", ".netrc", "_netrc", ".pgpass", ".npmrc", ".pypirc", ".git-credentials",
                "*.ppk", "*password*.csv", "*passwords*", "*.asc", "*.gpg")

@dataclass(frozen=True)
class Masked:
    """One masked value: the rule and where its mask stands in the masked text, the value's length. No hash of the
    value: an unsalted hash of a short password or a one-time code is guessed offline (security review 2026-11-15)."""
    rule: str
    at: int
    length: int

    def to_dict(self) -> dict:
        return {"rule": self.rule, "at": self.at, "length": self.length}

    @classmethod
    def from_dict(cls, d: dict) -> "Masked":
        return cls(str(d["rule"]), int(d["at"]), int(d["length"]))


def is_secret_file(path: str) -> bool:
    """A path whose content is secret: its name matches SECRET_FILES, or it is -- or lies in -- a secret folder (``tar
    ~/.ssh`` reads every key in it; imperal-mcp held this rule, the SDK's had lost it, 2026-11-15)."""
    parts = [p for p in str(path or "").replace("\\", "/").lower().split("/") if p]   # .ENV on a case-blind disk too
    if not parts:
        return False
    names = [p for p in SECRET_FILES if not p.endswith("/")]
    dirs = {p[:-1] for p in SECRET_FILES if p.endswith("/")}
    return any(fnmatch.fnmatchcase(parts[-1], pat) for pat in names) or any(d in dirs for d in parts)


# ---- the rules: the union of the three sets that had drifted (kernel repo_memory, imperal-mcp secrets_scrub, the
# vault's secret_filter, as of 2026-11-14). A mask is ``<redacted:KIND>`` -- the vault's form: it says what was there.

MASK = "<redacted:{}>"

_PEM = re.compile(r"-----BEGIN [A-Z0-9 ]{0,40}PRIVATE KEY-----.*?(?:-----END [A-Z0-9 ]{0,40}PRIVATE KEY-----|\Z)", re.S)
# known key formats (the vault's list, plus the generic hyphenated `sk-` body: sk-ant-api03-..., sk-proj-...)
_TOKENS = (
    ("anthropic-key", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}")),
    ("openai-key", re.compile(r"\bsk-(?:proj-|svcacct-|admin-)?[A-Za-z0-9_\-]{20,}")),
    ("stripe-key", re.compile(r"\b(?:sk|rk|pk)_(?:live|test)_[A-Za-z0-9]{10,}")),
    ("stripe-webhook-secret", re.compile(r"\bwhsec_[A-Za-z0-9]{16,}")),
    ("github-token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{40,})")),
    ("gitlab-token", re.compile(r"\bglpat-[A-Za-z0-9_\-]{20,}")),
    ("slack-token", re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}")),
    ("aws-access-key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("telegram-bot-token", re.compile(r"\b\d{8,10}:AA[A-Za-z0-9_\-]{33}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+")),
    ("vault-token", re.compile(r"\bhv[sbr]\.[A-Za-z0-9_\-]{20,}")),
    ("bearer", re.compile(r"(?i)(?<=bearer )[A-Za-z0-9._\-]{10,}")),
)
# a password on a command line: the MySQL clients take it glued to ``-p``, sshpass after ``-p``; ``mkdir -p`` stays
_CLI_MYSQL_PW = re.compile(r"(\b(?:mysql|mysqldump|mariadb|mariadb-dump|mysqladmin|mysqlimport|mysqlcheck)\b"
                           r"[^|;&\n]*?\s-p)('[^'\n]*'|\"[^\"\n]*\"|[^\s'\"]+)")
_CLI_SSHPASS = re.compile(r"(\bsshpass\s+-p\s*)('[^'\n]*'|\"[^\"\n]*\"|\S+)")
# a password in a URL: the scheme and the user stay (``postgres://app:<redacted:url-password>@db``)
_URL_PASSWORD = re.compile(r"(?i)(?<![a-z0-9+.-])([a-z][a-z0-9+.\-]{0,31}://[^\s:/@'\"<>]*:)([^\s@/'\"<>]+)(@)")
# a token alone as URL user-info (``https://ghp_x@github.com``): a user name before ``@`` with no password
_URL_TOKEN = re.compile(r"(?i)(?<![a-z0-9+.-])([a-z][a-z0-9+.-]{0,31}://)([^\s/@:]{8,})(@)")
# the credential after an auth scheme or in a token header
_AUTH_HEADER = re.compile(r"(?i)\b((?:proxy-)?authorization[\"']?\s*[:=]\s*[\"']?(?:(?:basic|bearer|token|digest|"
                          r"negotiate)\s+)?|x-(?:service|api|vault|auth|access)-(?:token|key)\s*:\s*)([^\s\"',;]+)")
# a key NAMED like a secret keeps its name and loses its value; ``pass``/``pwd`` only as a whole part of the name
_SECRET_NAME = (r"(?:api[_-]?key|private[_-]?key|access[_-]?key|client[_-]?secret|secret|token(?![a-z])|"
                r"passw(?:or)?d|passphrase|authorization|bearer|credentials?|dsn|hmac|salt|"
                r"(?<![a-z])pass(?![a-z])|(?<![a-z])pwd(?![a-z]))")
_KEYWORD = re.compile(r"""(?i)(?<![A-Za-z0-9_.-])([A-Za-z0-9_.-]{0,48}?""" + _SECRET_NAME + r"""[A-Za-z0-9_.-]{0,48})"""
                      r"""(["']?[ \t]*[:=][ \t]*["']?)([^\s"'`,;]+)""")
# a secret-named key in any case with an unquoted random-looking value (yaml, logs: ``password: Kq7L9x...``)
_ASSIGN_ANY = re.compile(r"(?i)\b([a-z0-9_.-]{0,48}" + _SECRET_NAME + r"[a-z0-9_.-]{0,48})(\s*[=:]\s*)([^\s'\"`,;]{16,})")
# a setting ABOUT a secret, not the secret: SECRET_NAME, TOKEN_ID, MAX_TOKENS, AUTH_TOKEN_TTL ...
_NOT_A_SECRET_NAME = re.compile(
    r"(?i)(?:^(?:MAX|MIN|NUM|N|DEFAULT)_|_(?:NAME|NAMES|ID|IDS|PROVIDER|HEADER|HEADERS|REJECTED|TYPE|KIND|PATH|FILE|"
    r"TTL|EXPIRY|EXPIRES|EXPIRE|COUNT|LIMIT|LEN|LENGTH|MODE|FIELD|PREFIX|ENV|VAR|SCOPE|SCOPES|URL|URI|ENDPOINT|"
    r"ENABLED|REQUIRED|VERSION|ALGORITHM|FORMAT|LABEL|KEY_ID|ROTATION|RE|REGEX|PATTERN)$|^TOKENS$|_TOKENS$)")
_CODE_VALUE = re.compile(r"^[A-Za-z_][\w.]{0,128}[(\[][^&;=,]*$")      # the WHOLE value is a call/subscript
_TOKEN_ONLY = re.compile(r"(?i)token(?![a-z])")
# the same names but "token": a key secret by another word too (secret_token, auth_token_password) is never a measure
_OTHER_SECRET = re.compile(r"(?i)" + _SECRET_NAME.replace("token(?![a-z])|", ""))
_DECIMAL = re.compile(r"^\d+\.\d+[,;)}\]]*$")
_DOTTED = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+")
_PLACEHOLDERS = frozenset({"changeme", "password123", "your_password_here", "xxxxxxxxxxxx"})

# a mask in the making: \x00<n>\x00 never occurs in a decoded text (normalise_text refuses NUL), and no rule matches it
_SLOT = re.compile(r"\x00(\d+)\x00")


def strong(value: str) -> bool:
    """A random-looking credential, whatever it is named: long, letters AND digits, high entropy, not code."""
    if len(value) < 16 or re.search(r"[()\[\]{}<>$]", value) or _DOTTED.fullmatch(value) or _SLOT.search(value):
        return False
    if not (any(c.isdigit() for c in value) and any(c.isalpha() for c in value)):
        return False
    segs = [x for x in re.split(r"[_\-.]", value) if x]
    if len(segs) >= 2 and any(x.isalpha() and len(x) >= 4 for x in segs) and all(x.isalpha() or len(x) <= 3 for x in segs):
        return False                     # words joined by _ - . (anthropic_default_x9): a name, not a key
    counts = {c: value.count(c) for c in set(value)}
    return -sum(n / len(value) * math.log2(n / len(value)) for n in counts.values()) >= 3.5


_LITERALS = frozenset({"none", "null", "nil", "true", "false", "undefined", "''", '""'})
_CONSTANT = re.compile(r"[A-Z][A-Z0-9_]{2,}")


def _keyword_secret(key: str, sep: str, val: str, code: bool) -> bool:
    """Is a secret-named key's value a secret? The kernel's, imperal-mcp's and the vault's rules as one:
    - a random-looking value: always;
    - a quoted literal: yes (``password="hunter2"``), unless a placeholder or a template;
    - unquoted: not in source code (``code``), not code itself (a call, a subscript, a dotted name, a CONSTANT, a
      literal like None), not the key's own name, not a measure under "token" (seconds to the first token), not a
      setting ABOUT a secret (SECRET_NAME, TOKEN_TTL, MAX_TOKENS); an env-style KEY's value yes; under any other key a
      value with a digit or a symbol yes, a plain word no (``passwd: files``, ``password: str``)."""
    if strong(val):
        return True
    if val.lower() in _PLACEHOLDERS or set(val) <= {"x", "X", "*"} or val.startswith(("<", "{", "$", "%(")):
        return False
    if sep.rstrip().endswith(("'", '"')):
        return True
    if code or _CODE_VALUE.match(val) or _DOTTED.fullmatch(val) or _CONSTANT.fullmatch(val):
        return False
    if val.lower() in _LITERALS or val.lower() == re.split(r"[_.-]", key)[-1].lower():
        return False
    if _TOKEN_ONLY.search(key) and not _OTHER_SECRET.search(key) and _DECIMAL.match(val):
        return False
    if _NOT_A_SECRET_NAME.search(key):
        return False
    if key.isupper():
        return True
    return any(c.isdigit() or (not c.isalnum() and c not in "_-.") for c in val)


class _Masker:
    def __init__(self, text: str):
        self.text = text
        self.found: list = []          # (kind, value)

    def slot(self, kind: str, value: str) -> str:
        self.found.append((kind, value))
        return f"\x00{len(self.found) - 1}\x00"

    def pem(self) -> None:
        # a key block keeps its line breaks: a code file's line numbers stay true
        self.text = _PEM.sub(lambda m: self.slot("private-key", m.group(0)) + "\n" * m.group(0).count("\n"),
                             self.text)

    def sub(self, kind: str, rx: "re.Pattern", keep: int | None = None, value: int = 0, tail: int | None = None):
        def repl(m):
            v = m.group(value)
            if _SLOT.search(v or ""):
                return m.group(0)
            return (m.group(keep) if keep else "") + self.slot(kind, v) + (m.group(tail) if tail else "")
        self.text = rx.sub(repl, self.text)

    def keyword(self, code: bool) -> None:
        def repl(m):
            key, sep, val = m.group(1), m.group(2), m.group(3)
            if _SLOT.search(val) or not _keyword_secret(key, sep, val, code):
                return m.group(0)
            return key + sep + self.slot("assigned-secret", val)
        self.text = _KEYWORD.sub(repl, self.text)
        self.text = _ASSIGN_ANY.sub(lambda m: m.group(1) + m.group(2) + self.slot("assigned-secret", m.group(3))
                                    if strong(m.group(3)) else m.group(0), self.text)

    def finish(self) -> tuple:
        out, masked, size = [], [], 0
        at = 0
        for m in _SLOT.finditer(self.text):
            piece = self.text[at:m.start()]
            out.append(piece)
            size += len(piece)
            kind, value = self.found[int(m.group(1))]
            mask = MASK.format(kind)
            masked.append(Masked(kind, size, len(value)))
            out.append(mask)
            size += len(mask)
            at = m.end()
        out.append(self.text[at:])
        return "".join(out), tuple(masked)


SCRUB_MEMO = 2048
SCRUB_MEMO_CHARS = 16_000      # a longer text is masked each time: the memo stays ~32 MB at most a process


@functools.lru_cache(maxsize=SCRUB_MEMO)
def _mask(text: str, code: bool) -> tuple:
    return _rules(_Masker(text), code)


def _rules(m: "_Masker", code: bool) -> tuple:
    m.pem()
    m.sub("cli-password", _CLI_MYSQL_PW, keep=1, value=2)
    m.sub("cli-password", _CLI_SSHPASS, keep=1, value=2)
    m.sub("url-password", _URL_PASSWORD, keep=1, value=2, tail=3)
    m.sub("url-token", _URL_TOKEN, keep=1, value=2, tail=3)
    m.sub("auth-header", _AUTH_HEADER, keep=1, value=2)
    for kind, rx in _TOKENS:
        m.sub(kind, rx)
    m.keyword(code)
    return m.finish()


def mask(text: str, code: bool = False) -> tuple:
    """``(masked_text, masked)``: every secret shape replaced by its mask; ``masked`` names each (rule, where the mask
    stands in the masked text, the value's length). ``code``: the text is source code -- a secret-named
    key keeps an unquoted value (an identifier, a type, an expression)."""
    s = str(text or "")
    return _mask(s, bool(code)) if len(s) <= SCRUB_MEMO_CHARS else _mask.__wrapped__(s, bool(code))


def scrub_secrets(text: str, code: bool = False) -> str:
    """The masked text alone (what a model, a log or a stored note gets)."""
    return mask(text, code)[0]


# ---- a secret file's content (owner 2026-11-15, phase 6 decision 1): shown by its FORM, never by guessing which value
# looks secret. A settings file keeps each key's name and loses every value (``X=hunter2`` -> ``X=<redacted:...>``,
# whatever the value looks like); key material keeps nothing but its line count.

# files whose whole content is the secret (a key, a certificate, a keystore, a VPN profile) and the ssh folder
KEY_MATERIAL = ("*.pem", "*.key", "*.crt", "id_*", "*.p12", "*.pfx", "*.kdbx", "*.kdb", "*.keychain", "*.keychain-db",
                "*.ovpn", "*.mobileconfig", "wallet.dat", "*.ppk", "*.asc", "*.gpg", ".ssh/")
# a line of a settings file: its key keeps its name (KEY=..., export KEY=..., key: ..., "key": ...)
_SETTING = re.compile(r"""^([ \t]*(?:export[ \t]+)?)("?)([A-Za-z_][A-Za-z0-9_.\-]{0,63})("?[ \t]*[=:][ \t]*)(.*)$""")
_STRUCTURE = re.compile(r"^[\s{}\[\],]*$|^[ \t]*\[[A-Za-z0-9_. \-\"']{1,64}\][ \t]*$")   # braces, an [ini section]
_COMMENT = re.compile(r"^([ \t]*(?:#|;|//)[ \t]?)(.+)$")


def is_key_material(path: str) -> bool:
    """A secret file that is the secret whole (``KEY_MATERIAL``): nothing of it is shown but its line count."""
    parts = [p for p in str(path or "").replace("\\", "/").lower().split("/") if p]
    if not parts:
        return False
    names = [p for p in KEY_MATERIAL if not p.endswith("/")]
    dirs = {p[:-1] for p in KEY_MATERIAL if p.endswith("/")}
    return any(fnmatch.fnmatchcase(parts[-1], pat) for pat in names) or any(d in dirs for d in parts)


def _settings(m: "_Masker") -> None:
    """Every value of every line masked, its key kept; a line that is no ``key = value`` (a PEM line, a netrc line, a
    bare token) masked whole; a comment's words masked (an old password noted there); blank and brace lines kept."""
    out = []
    for line in m.text.split("\n"):
        body, cr = (line[:-1], "\r") if line.endswith("\r") else (line, "")
        s = _SETTING.match(body)
        c = _COMMENT.match(body)
        if not body.strip() or _STRUCTURE.match(body):
            out.append(body)
        elif s and not strong(s.group(3)):          # a base64 line ending in '=' is no key
            value = s.group(5)
            out.append(s.group(1) + s.group(2) + s.group(3) + s.group(4)
                       + (m.slot("secret-file-value", value) if value.strip() not in ("", "{", "[", "|", ">") else value))
        elif c:
            out.append(c.group(1) + m.slot("secret-file-comment", c.group(2)))
        else:
            out.append(m.slot("secret-file-line", body))
        out[-1] += cr
    m.text = "\n".join(out)


def secret_file_view(text: str, path: str = "") -> tuple:
    """``(masked_text, masked)`` of a secret file's content (``is_secret_file(path)``) or of a command's output that
    prints secrets (``path`` empty): key material (``is_key_material``) is one mask and its line breaks; anything else
    is a settings file -- each key's name stays, each value is masked whatever it looks like. The usual rules run after
    (a token in a key's name is still caught). Line count is kept: a line number stays true."""
    t = str(text or "")
    if path and is_key_material(path):
        if not t:
            return "", ()
        head = MASK.format("key-file")
        return head + "\n" * t.count("\n"), (Masked("key-file", 0, len(t)),)
    m = _Masker(t)
    _settings(m)
    return _rules(m, False)


def scrub_secret_file(text: str, path: str = "") -> str:
    """The masked text alone of ``secret_file_view``."""
    return secret_file_view(text, path)[0]


SECRET_VALUE_MIN = 3     # a shorter value (0, 1, on) is no secret, and masking it would mask every such word around


def secret_file_values(text: str, path: str = "") -> list:
    """The values a secret file holds -- what ``secret_file_view`` masks in it (key material: each of its lines), longest
    first: a command that used the file (``. .env; ./bench``) has exactly these masked in its output, the rest of the
    output stays a fact."""
    t = str(text or "")
    if path and is_key_material(path):
        vals = [x.strip() for x in t.splitlines()]
    else:
        m = _Masker(t)
        _settings(m)
        _rules(m, False)
        vals = [str(v).strip().strip("\"'") for _, v in m.found] + [str(v).strip() for _, v in m.found]
    return sorted({v for v in vals if len(v) >= SECRET_VALUE_MIN}, key=len, reverse=True)


_WORD_TOKEN = re.compile(r"(?<![A-Za-z0-9+/=_\-])[A-Za-z0-9+/=_\-]{16,}(?![A-Za-z0-9+/=_\-])")


def mask_values(text: str, values) -> tuple:
    """``(masked_text, masked)``: every occurrence of each of ``values`` masked (``secret-file-value``); then any
    random-looking token alone (``strong``: a value passed through base64 or hex no longer equals itself); then the usual
    rules."""
    m = _Masker(str(text or ""))
    for v in sorted({str(x) for x in values or () if len(str(x)) >= SECRET_VALUE_MIN}, key=len, reverse=True):
        if v in m.text:      # never inside a mask already made (its slot number may hold the same digits)
            parts = re.split(r"(\x00\d+\x00)", m.text)
            m.text = "".join(p if _SLOT.fullmatch(p) else p.replace(v, m.slot("secret-file-value", v)) for p in parts)
    m.text = _WORD_TOKEN.sub(lambda t: m.slot("secret-like", t.group(0)) if strong(t.group(0)) else t.group(0), m.text)
    return _rules(m, False)


_CODE_EXT = frozenset({"py", "pyi", "js", "jsx", "mjs", "cjs", "ts", "tsx", "go", "rs", "java", "kt", "kts", "scala",
                       "rb", "php", "c", "h", "cc", "cpp", "hpp", "cs", "swift", "m", "mm", "dart", "lua", "vue",
                       "svelte", "ex", "exs", "erl", "clj", "hs", "ml", "fs", "r", "jl", "pl", "pm"})
_FILE_HEAD = re.compile(r"^=== (\S+?)(?: \[[^\]]*\])?(?: \((?:whole|\d+ lines)[^)]*\))? ===$", re.M)


def is_code_path(path: str) -> bool:
    name = str(path or "").replace("\\", "/").rsplit("/", 1)[-1].lower()
    return "." in name and not name.startswith(".env") and name.rsplit(".", 1)[-1] in _CODE_EXT


def scrub_file_text(text: str, path: str = "") -> str:
    """A file's text scrubbed as what it is: source code by its extension, anything else strictly. A text holding
    several ``=== <path> ... ===`` sections is scrubbed section by section."""
    t = str(text or "")
    heads = list(_FILE_HEAD.finditer(t))
    if not heads:
        return scrub_secrets(t, code=is_code_path(path))
    out = [scrub_secrets(t[:heads[0].start()])]
    for i, h in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(t)
        out.append(h.group(0) + scrub_secrets(t[h.end():end], code=is_code_path(h.group(1))))
    return "".join(out)
