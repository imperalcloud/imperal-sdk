"""Views of text, markup and data files: plain text, Markdown, reStructuredText, HTML, RTF, CSV/TSV, JSON, YAML,
TOML, XML. Headings, header rows and keys are read by each format's own syntax (mechanical formats, never meaning).
"""
from __future__ import annotations

import csv
import io
import json
from html.parser import HTMLParser

from imperal_sdk.universal.view import UnsafeXML, View, close_sections, decode, line_count, parse_xml, register

TREE_DEPTH = 3            # keys of JSON / YAML / TOML / XML named in the outline down to this depth
CSV_MAX_ROWS = 200_000


def _text_or_skip(raw: bytes) -> str | None:
    return decode(raw)


def _plain(rel: str, raw: bytes) -> View:
    text = _text_or_skip(raw)
    return View("document", text or "", skipped="" if text is not None else "not text")


def _markdown(rel: str, raw: bytes) -> View:
    text = _text_or_skip(raw)
    if text is None:
        return View("document", "", skipped="not text")
    heads, fenced = [], False
    for n, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
            continue
        if fenced:
            continue
        marks = len(line) - len(line.lstrip("#"))
        if 1 <= marks <= 6 and line[marks:marks + 1] == " " and line[marks:].strip():
            heads.append((line[marks:].strip().rstrip("#").strip(), "section", marks, n))
    return View("document", text, close_sections(heads, line_count(text)))


_RST_UNDERLINES = set("=-~^\"'`#*+:._")


def _rst(rel: str, raw: bytes) -> View:
    text = _text_or_skip(raw)
    if text is None:
        return View("document", "", skipped="not text")
    lines = text.splitlines()
    order: list[str] = []
    heads = []
    for i in range(len(lines) - 1):
        title, under = lines[i].strip(), lines[i + 1].rstrip()
        if title and under and len(set(under)) == 1 and under[0] in _RST_UNDERLINES and len(under) >= len(title):
            if under[0] not in order:
                order.append(under[0])
            heads.append((title, "section", order.index(under[0]) + 1, i + 1))
    return View("document", text, close_sections(heads, line_count(text)))


class _Html(HTMLParser):
    _BLOCK = {"p", "div", "br", "li", "tr", "section", "article", "table", "ul", "ol", "header", "footer",
              "h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lines: list[str] = [""]
        self.heads: list[tuple[str, str, int, int]] = []
        self.links: list[str] = []
        self._skip = 0
        self._head: tuple[int, list[str]] | None = None

    def _newline(self):
        if self.lines[-1].strip():
            self.lines.append("")

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self._skip += 1
        if tag in self._BLOCK:
            self._newline()
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._head = (int(tag[1]), [])
        if tag == "a":
            href = dict(attrs).get("href")
            if href and not href.startswith(("#", "javascript:")):
                self.links.append(href)

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self._skip:
            self._skip -= 1
        if self._head and tag == f"h{self._head[0]}":
            title = " ".join("".join(self._head[1]).split())
            if title:
                self.heads.append((title, "section", self._head[0], len(self.lines)))
            self._head = None
        if tag in self._BLOCK:
            self._newline()

    def handle_data(self, data):
        if self._skip:
            return
        if self._head is not None:
            self._head[1].append(data)
        self.lines[-1] += data


def _html(rel: str, raw: bytes) -> View:
    text = _text_or_skip(raw)
    if text is None:
        return View("document", "", skipped="not text")
    p = _Html()
    p.feed(text)
    p.close()
    out = "\n".join(" ".join(ln.split()) for ln in p.lines).strip("\n")
    return View("document", out, close_sections(p.heads, line_count(out)), list(dict.fromkeys(p.links)))


_RTF_SKIP_GROUPS = {"fonttbl", "colortbl", "stylesheet", "info", "pict", "object", "header", "footer"}


def _rtf(rel: str, raw: bytes) -> View:
    """RTF to text: control words dropped, ``\\par`` / ``\\line`` as new lines, ``\\'hh`` as cp1252, the font,
    colour, style and info tables and ``{\\*...}`` destinations skipped."""
    s = raw.decode("latin-1")
    out: list[str] = []
    stack: list[bool] = []
    skip = False
    i, n = 0, len(s)
    while i < n:
        c = s[i]
        if c == "{":
            stack.append(skip)
            if s.startswith("{\\*", i):
                skip = True
            i += 1
        elif c == "}":
            skip = stack.pop() if stack else False
            i += 1
        elif c == "\\":
            if i + 1 < n and s[i + 1] in "\\{}":
                if not skip:
                    out.append(s[i + 1])
                i += 2
            elif i + 1 < n and s[i + 1] == "'":
                if not skip:
                    out.append(bytes([int(s[i + 2:i + 4], 16)]).decode("cp1252", "replace"))
                i += 4
            else:
                j = i + 1
                while j < n and s[j].isalpha():
                    j += 1
                word = s[i + 1:j]
                while j < n and (s[j].isdigit() or s[j] == "-"):
                    j += 1
                if j < n and s[j] == " ":
                    j += 1
                if word in _RTF_SKIP_GROUPS:
                    skip = True
                elif word in ("par", "line") and not skip:
                    out.append("\n")
                elif word == "tab" and not skip:
                    out.append("\t")
                i = j
        else:
            if not skip and c not in "\r\n":
                out.append(c)
            i += 1
    text = "\n".join(" ".join(ln.split()) for ln in "".join(out).split("\n")).strip()
    return View("document", text)


def _table(rel: str, raw: bytes) -> View:
    text = _text_or_skip(raw)
    if text is None:
        return View("data", "", skipped="not text")
    delim = "\t" if rel.lower().endswith(".tsv") else ","
    rows = []
    for i, row in enumerate(csv.reader(io.StringIO(text), delimiter=delim)):
        if i >= CSV_MAX_ROWS:
            break
        rows.append(" | ".join(cell.strip() for cell in row))
    out = "\n".join(rows)
    if not rows:
        return View("data", "")
    header = [c.strip() for c in next(csv.reader(io.StringIO(text.split("\n", 1)[0]), delimiter=delim), [])]
    head = ("columns: " + ", ".join(header), "table", 1, 1)
    return View("data", out, close_sections([head], line_count(out)))


def _render_tree(data) -> tuple[str, list[tuple[str, str, int, int]]]:
    """A nested value as indented ``key: value`` lines; every mapping key down to ``TREE_DEPTH`` is a head."""
    lines: list[str] = []
    heads: list[tuple[str, str, int, int]] = []

    def scalar(v) -> bool:
        return not isinstance(v, (dict, list)) or not v

    def show(v) -> str:
        return json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else str(v)

    def walk(obj, path: str, depth: int):
        pad = "  " * depth
        if isinstance(obj, dict):
            for k, v in obj.items():
                name = f"{path}.{k}" if path else str(k)
                lines.append(f"{pad}{k}: {show(v)}" if scalar(v) else f"{pad}{k}:")
                if depth < TREE_DEPTH:
                    heads.append((name, "key", depth + 1, len(lines)))
                if not scalar(v):
                    walk(v, name, depth + 1)
        elif isinstance(obj, list):
            for item in obj:
                if scalar(item):
                    lines.append(f"{pad}- {show(item)}")
                else:
                    lines.append(f"{pad}-")
                    walk(item, path, depth + 1)
        else:
            lines.append(f"{pad}{show(obj)}")
    walk(data, "", 0)
    return "\n".join(lines), heads


def _tree_view(text: str, data) -> View:
    out, heads = _render_tree(data)
    return View("data", out, close_sections(heads, line_count(out)))


def _json(rel: str, raw: bytes) -> View:
    text = _text_or_skip(raw)
    if text is None:
        return View("data", "", skipped="not text")
    try:
        return _tree_view(text, json.loads(text))
    except ValueError:
        return View("data", "", skipped="not valid JSON")


def _yaml(rel: str, raw: bytes) -> View:
    text = _text_or_skip(raw)
    if text is None:
        return View("data", "", skipped="not text")
    try:
        import yaml
    except ImportError:
        return View("data", text)              # no YAML reader installed: the text, without an outline
    try:
        return _tree_view(text, yaml.safe_load(text))
    except Exception:
        return View("data", text, meta={"outline": "not valid YAML"})


def _toml(rel: str, raw: bytes) -> View:
    text = _text_or_skip(raw)
    if text is None:
        return View("data", "", skipped="not text")
    import tomllib
    try:
        return _tree_view(text, tomllib.loads(text))
    except Exception:
        return View("data", text, meta={"outline": "not valid TOML"})


def _xml(rel: str, raw: bytes) -> View:
    try:
        root = parse_xml(raw)
    except UnsafeXML:
        return View("data", "", skipped="XML with a DOCTYPE is not read")
    except Exception:
        text = _text_or_skip(raw)
        return View("data", text or "", skipped="" if text else "not valid XML")
    lines: list[str] = []
    heads: list[tuple[str, str, int, int]] = []

    def walk(el, path: str, depth: int):
        tag = el.tag.rsplit("}", 1)[-1]
        name = f"{path}.{tag}" if path else tag
        body = " ".join((el.text or "").split())
        lines.append(f"{'  ' * depth}{tag}: {body}" if body else f"{'  ' * depth}{tag}")
        if depth < TREE_DEPTH:
            heads.append((name, "key", depth + 1, len(lines)))
        for child in el:
            walk(child, name, depth + 1)
    walk(root, "", 0)
    out = "\n".join(lines)
    return View("data", out, close_sections(heads, line_count(out)))


register((".txt",), _plain)
register((".md", ".markdown"), _markdown)
register((".rst",), _rst)
register((".html", ".htm"), _html)
register((".rtf",), _rtf)
register((".csv", ".tsv"), _table)
register((".json",), _json)
register((".yaml", ".yml"), _yaml)
register((".toml",), _toml)
register((".xml",), _xml)
