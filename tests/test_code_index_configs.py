"""The one reader of resolution configs (tsconfig/jsconfig are JSON with comments): comments and trailing
commas go, strings stay whole -- live 2026-11-03, imperal.io's ``"@/*"`` was read as a comment opener."""
from imperal_sdk.code_index import parse_config, parse_jsonc, strip_jsonc

# imperal.io's own tsconfig.json (Next.js 16), verbatim in shape: "@/*" and "**/*.ts" in strings
NEXT_TSCONFIG = """{
  "compilerOptions": {
    "target": "ES2017",
    "lib": ["dom", "dom.iterable", "esnext"],
    "strict": true,
    "plugins": [
      {
        "name": "next"
      }
    ],
    "paths": {
      "@/*": ["./src/*"]
    }
  },
  "include": [
    "next-env.d.ts",
    "**/*.ts",
    "**/*.tsx",
    ".next/types/**/*.ts"
  ],
  "exclude": ["node_modules"]
}
"""


def test_next_tsconfig_keeps_its_paths():
    kind, data = parse_config("tsconfig.json", NEXT_TSCONFIG)
    assert kind == "tsconfig"
    assert data == {"baseUrl": "", "paths": {"@/*": ["./src/*"]}}


def test_comments_and_trailing_commas_go_outside_strings_only():
    text = """{
      // a line comment with "quotes" and /* inside
      "compilerOptions": {
        /* a block comment
           over lines, with "@/*" text */
        "baseUrl": ".", // after a value
        "paths": {"~/*": ["src/*",], "url": ["https://example.com/a//b"],},
      },
    }"""
    data = parse_jsonc(text)
    assert data["compilerOptions"]["baseUrl"] == "."
    assert data["compilerOptions"]["paths"] == {"~/*": ["src/*"], "url": ["https://example.com/a//b"]}


def test_escaped_quotes_and_backslashes_stay_inside_the_string():
    text = '{"a": "say \\"/*\\" not a comment", "b": "c:\\\\dir\\\\", "c": 1,}'
    assert parse_jsonc(text) == {"a": 'say "/*" not a comment', "b": "c:\\dir\\", "c": 1}


def test_a_comma_before_a_comment_then_a_brace_is_trailing():
    assert parse_jsonc('{"a": [1, 2, /* end */ ], "b": 3, // last\n}') == {"a": [1, 2], "b": 3}


def test_not_an_object_is_empty():
    assert parse_jsonc("[1, 2]") == {}
    assert parse_jsonc("{ broken") == {}
    assert strip_jsonc("") == ""


def test_package_json_and_jsconfig():
    assert parse_config("web/package.json", '{"name": "web", "main": "index.js", // c\n}') == (
        "package_json", {"name": "web", "main": "index.js"})
    assert parse_config("jsconfig.json", '{"compilerOptions": {"baseUrl": "src"}}')[0] == "jsconfig"
