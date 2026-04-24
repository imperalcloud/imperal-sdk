# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""V14 validator: rejects v1-style extensions.

Covers every v1-era marker tracked by the v2.0.0 loader:
  - ChatExtension import from imperal_sdk
  - imperal_sdk.ChatExtension attribute access
  - class-level _system_prompt assignment
  - module-level _system_prompt assignment
  - llm_orchestrator=True keyword arg in any call
  - prompts/system_prompt.txt file
  - prompts/intake.txt file

Invariants: I-LOADER-REJECT-CHATEXT, I-LOADER-REJECT-SYSTEM-PROMPT,
I-LOADER-REJECT-ORCHESTRATOR.
"""
from imperal_sdk.validators.v14_no_chatext import run_v14


def test_v14_passes_clean_ext(tmp_path):
    ext_dir = tmp_path / "good_ext"
    ext_dir.mkdir()
    (ext_dir / "main.py").write_text(
        "from imperal_sdk import Extension, ext\n"
        "from pydantic import BaseModel\n"
        "\n"
        "class Out(BaseModel):\n"
        "    x: int\n"
        "\n"
        "class GoodExt(Extension):\n"
        "    @ext.tool(description=\"Twenty characters minimum description here\", output_schema=Out)\n"
        "    async def do(self):\n"
        "        return Out(x=1)\n"
    )
    result = run_v14(ext_dir)
    assert result.passed
    assert result.issues == []


def test_v14_rejects_chatextension_import(tmp_path):
    ext_dir = tmp_path / "bad_ext"
    ext_dir.mkdir()
    (ext_dir / "main.py").write_text(
        "from imperal_sdk import ChatExtension, ext\n"
        "class BadExt(ChatExtension): pass\n"
    )
    result = run_v14(ext_dir)
    assert not result.passed
    assert any("ChatExtension" in i for i in result.issues)


def test_v14_rejects_chatextension_attribute_access(tmp_path):
    ext_dir = tmp_path / "bad_ext"
    ext_dir.mkdir()
    (ext_dir / "main.py").write_text(
        "import imperal_sdk\n"
        "class BadExt(imperal_sdk.ChatExtension):\n"
        "    pass\n"
    )
    result = run_v14(ext_dir)
    assert not result.passed
    assert any("imperal_sdk.ChatExtension" in i for i in result.issues)


def test_v14_rejects_system_prompt_attr(tmp_path):
    ext_dir = tmp_path / "bad_ext"
    ext_dir.mkdir()
    (ext_dir / "main.py").write_text(
        "from imperal_sdk import Extension\n"
        "class BadExt(Extension):\n"
        "    _system_prompt = \"I am the legacy assistant\"\n"
    )
    result = run_v14(ext_dir)
    assert not result.passed
    assert any("_system_prompt" in i for i in result.issues)


def test_v14_rejects_module_level_system_prompt(tmp_path):
    ext_dir = tmp_path / "bad_ext"
    ext_dir.mkdir()
    (ext_dir / "main.py").write_text(
        "from imperal_sdk import Extension\n"
        "_system_prompt = \"module-level legacy\"\n"
        "class BadExt(Extension): pass\n"
    )
    result = run_v14(ext_dir)
    assert not result.passed
    assert any("_system_prompt" in i for i in result.issues)


def test_v14_rejects_system_prompt_txt(tmp_path):
    ext_dir = tmp_path / "bad_ext"
    ext_dir.mkdir()
    (ext_dir / "main.py").write_text(
        "from imperal_sdk import Extension\nclass X(Extension): pass\n"
    )
    (ext_dir / "prompts").mkdir()
    (ext_dir / "prompts" / "system_prompt.txt").write_text("I am the legacy assistant")
    result = run_v14(ext_dir)
    assert not result.passed
    assert any("system_prompt.txt" in i for i in result.issues)


def test_v14_rejects_intake_txt(tmp_path):
    ext_dir = tmp_path / "bad_ext"
    ext_dir.mkdir()
    (ext_dir / "main.py").write_text(
        "from imperal_sdk import Extension\nclass X(Extension): pass\n"
    )
    (ext_dir / "prompts").mkdir()
    (ext_dir / "prompts" / "intake.txt").write_text("persona intake")
    result = run_v14(ext_dir)
    assert not result.passed
    assert any("intake.txt" in i for i in result.issues)


def test_v14_rejects_llm_orchestrator_flag(tmp_path):
    ext_dir = tmp_path / "bad_ext"
    ext_dir.mkdir()
    (ext_dir / "main.py").write_text(
        "from imperal_sdk import Extension, ext\n"
        "from pydantic import BaseModel\n"
        "\n"
        "class Out(BaseModel):\n"
        "    x: int\n"
        "\n"
        "class BadExt(Extension):\n"
        "    @ext.tool(description=\"Twenty character description here\", output_schema=Out, llm_orchestrator=True)\n"
        "    async def orch(self):\n"
        "        return Out(x=1)\n"
    )
    result = run_v14(ext_dir)
    assert not result.passed
    assert any("llm_orchestrator" in i for i in result.issues)


def test_v14_llm_orchestrator_false_is_ok(tmp_path):
    """Only ``llm_orchestrator=True`` is the v1 marker — False is fine."""
    ext_dir = tmp_path / "ext"
    ext_dir.mkdir()
    (ext_dir / "main.py").write_text(
        "from imperal_sdk import Extension, ext\n"
        "from pydantic import BaseModel\n"
        "\n"
        "class Out(BaseModel):\n"
        "    x: int\n"
        "\n"
        "class OkExt(Extension):\n"
        "    @ext.tool(description=\"Twenty character description here\", output_schema=Out, llm_orchestrator=False)\n"
        "    async def do(self):\n"
        "        return Out(x=1)\n"
    )
    # Note: llm_orchestrator kwarg itself is a legacy marker in v2, but V14
    # explicitly only flags the ``True`` literal; the decorator layer will
    # still reject the kwarg as unknown.
    result = run_v14(ext_dir)
    # Should pass V14 specifically (not flag llm_orchestrator=False).
    assert result.passed, f"unexpected issues: {result.issues}"


def test_v14_scans_subdirectories(tmp_path):
    """AST scan is recursive."""
    ext_dir = tmp_path / "ext"
    ext_dir.mkdir()
    (ext_dir / "main.py").write_text(
        "from imperal_sdk import Extension\nclass E(Extension): pass\n"
    )
    pkg = ext_dir / "handlers"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "legacy.py").write_text(
        "from imperal_sdk import ChatExtension\n"
        "chat = ChatExtension\n"
    )
    result = run_v14(ext_dir)
    assert not result.passed
    # Issue should report the nested path.
    assert any("handlers/legacy.py" in i or "handlers\\legacy.py" in i for i in result.issues)


def test_v14_skips_pycache_and_venv(tmp_path):
    """Cache and venv dirs must be ignored."""
    ext_dir = tmp_path / "ext"
    ext_dir.mkdir()
    (ext_dir / "main.py").write_text(
        "from imperal_sdk import Extension\nclass E(Extension): pass\n"
    )
    for skip in ("__pycache__", "venv", ".venv"):
        d = ext_dir / skip
        d.mkdir()
        (d / "tainted.py").write_text(
            "from imperal_sdk import ChatExtension\n"
        )
    result = run_v14(ext_dir)
    assert result.passed, f"unexpected issues: {result.issues}"


def test_v14_handles_syntax_error(tmp_path):
    """A syntactically broken source file should add an issue, not crash."""
    ext_dir = tmp_path / "ext"
    ext_dir.mkdir()
    (ext_dir / "broken.py").write_text("def f(:\n")
    result = run_v14(ext_dir)
    assert not result.passed
    assert any("syntax error" in i for i in result.issues)


def test_v14_accepts_string_path(tmp_path):
    """run_v14 accepts both Path and str."""
    ext_dir = tmp_path / "ext"
    ext_dir.mkdir()
    (ext_dir / "main.py").write_text(
        "from imperal_sdk import Extension\nclass E(Extension): pass\n"
    )
    result = run_v14(str(ext_dir))
    assert result.passed
