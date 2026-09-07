import pytest
from imperal_sdk.pipes import Pipe, ExtensionPipe, PipeStep
from imperal_sdk.chat.extension import ChatExtension
from imperal_sdk.extension import Extension, ToolDef


def test_extension_pipe_composition():
    # Создаем пайплайн: stripe -> mailer -> telegram
    p = Pipe("stripe-connector", "get_invoice", customer_id="{customer_id}")
    p = p.pipe("mailer", "send_reminder", to="{email}")
    p = p | ("telegram-publisher", "send_alert")

    assert isinstance(p, ExtensionPipe)
    assert len(p.steps) == 3
    
    d = p.to_dict()
    assert d["type"] == "extension_pipe"
    assert d["steps"][0]["app_id"] == "stripe-connector"
    assert d["steps"][0]["tool_name"] == "get_invoice"
    assert d["steps"][1]["app_id"] == "mailer"
    assert d["steps"][2]["app_id"] == "telegram-publisher"


def test_chat_function_with_io_ports():
    ext = Extension("test-pipes")
    chat = ChatExtension(ext)

    @chat.function(
        name="analyze_sentiment",
        description="Analyzes customer feedback sentiment",
        inputs=["text/plain", "application/json"],
        outputs=["application/json"],
    )
    def analyze(text: str):
        return {"sentiment": "positive"}

    f_def = chat._functions["analyze_sentiment"]
    assert f_def.inputs == ["text/plain", "application/json"]
    assert f_def.outputs == ["application/json"]
