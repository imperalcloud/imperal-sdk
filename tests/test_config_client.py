# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
from imperal_sdk.config.client import ConfigClient


def test_get_simple():
    cfg = ConfigClient({"models": {"primary_model": "claude-opus"}, "pii": True})
    assert cfg.get("pii") is True


def test_get_dot_notation():
    cfg = ConfigClient({"models": {"primary_model": "claude-opus", "temperature": 0.7}})
    assert cfg.get("models.primary_model") == "claude-opus"
    assert cfg.get("models.temperature") == 0.7


def test_get_missing_returns_default():
    cfg = ConfigClient({"models": {}})
    assert cfg.get("models.missing") is None
    assert cfg.get("models.missing", "fallback") == "fallback"
    assert cfg.get("nonexistent.deep.key", 42) == 42


def test_get_section():
    cfg = ConfigClient({"models": {"primary_model": "opus", "temp": 0.7}, "alerts": {"enabled": True}})
    section = cfg.get_section("models")
    assert section == {"primary_model": "opus", "temp": 0.7}
    section["primary_model"] = "sonnet"
    assert cfg.get("models.primary_model") == "opus"


def test_get_section_missing():
    cfg = ConfigClient({"models": {}})
    assert cfg.get_section("nonexistent") == {}


def test_all():
    data = {"models": {"primary_model": "opus"}, "pii": False}
    cfg = ConfigClient(data)
    result = cfg.all()
    assert result == data
    result["pii"] = True
    assert cfg.get("pii") is False


def test_empty_config():
    cfg = ConfigClient({})
    assert cfg.get("anything") is None
    assert cfg.get_section("anything") == {}
    assert cfg.all() == {}
