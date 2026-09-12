"""測試用：回固定內容或由 callable 產生；記錄每次呼叫（prompt、幾張圖、system）。"""
from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from typing import Any

from .base import LLMProvider, LLMResponse


class MockProvider(LLMProvider):
    name = "mock"
    model = "mock"

    def __init__(self, response: Any = None, handler: Callable[[str, Sequence[bytes], str | None], Any] | None = None):
        self._response = response
        self._handler = handler
        self.calls: list[dict[str, Any]] = []

    def complete(self, prompt: str, *, images: Sequence[bytes] = (), system: str | None = None,
                 max_tokens: int = 16000) -> LLMResponse:
        self.calls.append({"prompt": prompt, "n_images": len(images), "system": system})
        out = self._handler(prompt, images, system) if self._handler else self._response
        text = out if isinstance(out, str) else json.dumps(out, ensure_ascii=False)
        return LLMResponse(text=text, provider=self.name, model=self.model)
