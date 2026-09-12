"""Anthropic 官方 API。模型預設 claude-opus-5；圖片以 base64 image block 送，文字放最後。"""
from __future__ import annotations

import base64
import os
from collections.abc import Sequence

from .base import LLMError, LLMNotConfigured, LLMProvider, LLMResponse

DEFAULT_MODEL = "claude-opus-5"


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, api_key: str | None = None, model: str | None = None, timeout: float = 120.0):
        self.model = model or os.environ.get("ANTHROPIC_MODEL_ID") or DEFAULT_MODEL
        key = api_key or os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
        if not key:
            raise LLMNotConfigured("缺 ANTHROPIC_API_KEY")
        try:
            import anthropic
        except ImportError as e:  # pragma: no cover
            raise LLMNotConfigured("未安裝 anthropic 套件：pip install -e '.[llm]'") from e
        self._anthropic = anthropic
        self._client = anthropic.Anthropic(api_key=key, timeout=timeout, max_retries=2)

    def complete(self, prompt: str, *, images: Sequence[bytes] = (), system: str | None = None,
                 max_tokens: int = 16000) -> LLMResponse:
        content: list[dict] = [
            {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                         "data": base64.standard_b64encode(img).decode("ascii")}}
            for img in images
        ]
        content.append({"type": "text", "text": prompt})
        kwargs: dict = {"model": self.model, "max_tokens": max_tokens, "messages": [{"role": "user", "content": content}]}
        if system:
            kwargs["system"] = system
        a = self._anthropic
        try:
            resp = self._client.messages.create(**kwargs)
        except a.AuthenticationError as e:
            raise LLMNotConfigured(f"Anthropic 認證失敗：{e.message}") from e
        except a.RateLimitError as e:
            raise LLMError(f"Anthropic 額度限制：{e.message}") from e
        except a.APIStatusError as e:
            raise LLMError(f"Anthropic API 錯誤 {e.status_code}：{e.message}") from e
        except a.APIConnectionError as e:
            raise LLMError(f"Anthropic 連線失敗：{e}") from e
        if resp.stop_reason == "refusal":
            raise LLMError("模型拒絕回應（refusal）")
        text = "".join(b.text for b in resp.content if b.type == "text")
        usage = {"input_tokens": resp.usage.input_tokens, "output_tokens": resp.usage.output_tokens}
        return LLMResponse(text=text, provider=self.name, model=resp.model, usage=usage, raw=resp)
