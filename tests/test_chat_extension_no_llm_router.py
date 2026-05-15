"""Federal I-CHATEXTENSION-NO-LLM-ROUTER — class must not contain LLM-loop logic."""
import ast
import inspect
from imperal_sdk.chat.extension import ChatExtension


def test_chat_extension_has_no_handle_method():
    """ChatExtension MUST NOT define `_handle` (was LLM-loop entry)."""
    methods = {name for name, _ in inspect.getmembers(ChatExtension, predicate=inspect.isfunction)}
    assert "_handle" not in methods, (
        f"ChatExtension still defines _handle — must be removed in SDK 5.0.0. "
        f"Found methods: {methods}"
    )


def test_chat_extension_source_has_no_llm_complete_calls():
    """AST-scan ChatExtension class body for ctx.ai.complete / llm.complete calls."""
    src = inspect.getsource(ChatExtension)
    tree = ast.parse(src)
    cls_node = next(n for n in ast.walk(tree) if isinstance(n, ast.ClassDef))

    forbidden = ("ctx.ai.complete", "llm.complete", "client.complete", "messages.create")
    issues = []
    for node in ast.walk(cls_node):
        if isinstance(node, ast.Attribute):
            try:
                src_segment = ast.unparse(node)
            except Exception:
                continue
            for pat in forbidden:
                if pat in src_segment:
                    issues.append(src_segment)
    assert not issues, (
        f"ChatExtension class body contains forbidden LLM-completion calls: {issues}"
    )


def test_chat_handler_module_handle_message_removed():
    """`imperal_sdk.chat.handler.handle_message` MUST be removed in SDK 5.0.0.
    Either the module itself is deleted or handle_message is no longer exported.
    """
    try:
        import imperal_sdk.chat.handler as handler_mod
        # Module still exists — verify handle_message is gone:
        assert not hasattr(handler_mod, "handle_message"), (
            "handle_message remains in chat.handler — must be deleted in SDK 5.0.0"
        )
    except ImportError:
        # Module deleted entirely — preferred outcome, also valid.
        pass
