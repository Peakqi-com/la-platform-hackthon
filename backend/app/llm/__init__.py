"""get_provider()：依 LLM_PROVIDER 環境變數回傳 provider；provider_status() 給 /api/health 用（不建立連線）。"""
from __future__ import annotations

import os
from typing import Any, Optional  # noqa: F401

from .base import LLMError, LLMNotConfigured, LLMProvider, LLMResponse, parse_json_loose

__all__ = ["LLMError", "LLMNotConfigured", "LLMProvider", "LLMResponse", "get_provider", "parse_json_loose", "provider_status"]

_registry: dict[str, LLMProvider] = {}


def get_provider(name: str | None = None, **kw: Any) -> LLMProvider:
    name = (name or os.environ.get("LLM_PROVIDER") or "anthropic").strip().lower()
    if name in _registry and not kw:
        return _registry[name]
    if name == "anthropic":
        from .anthropic_provider import AnthropicProvider
        p: LLMProvider = AnthropicProvider(**kw)
    elif name == "bedrock":
        from .bedrock_provider import BedrockProvider
        p = BedrockProvider(**kw)
    elif name == "mock":
        from .mock_provider import MockProvider
        p = MockProvider(**kw)
    else:
        raise LLMNotConfigured(f"未知的 LLM_PROVIDER={name}（anthropic | bedrock | mock）")
    if not kw:
        _registry[name] = p
    return p


def set_provider(p: LLMProvider) -> None:
    """測試或 UI 切換用。"""
    _registry[p.name] = p
    os.environ["LLM_PROVIDER"] = p.name


def provider_status() -> dict[str, Any]:
    name = (os.environ.get("LLM_PROVIDER") or "anthropic").strip().lower()
    try:
        return get_provider(name).status()
    except LLMNotConfigured as e:
        return {"provider": name, "configured": False, "error": str(e)}
