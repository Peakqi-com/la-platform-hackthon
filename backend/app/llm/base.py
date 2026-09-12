"""
LLM provider 介面。只用在兩件事：PDF/掃描書表的 vision 抽取、審查意見書文字。規則引擎不碰這裡。

  LLM_PROVIDER=anthropic | bedrock | mock   （環境變數切換；預設 anthropic）
  ANTHROPIC_API_KEY / ANTHROPIC_MODEL_ID     （預設模型 claude-opus-5）
  AWS_REGION / BEDROCK_MODEL_ID              （當天依開通結果填；沒填 → LLMNotConfigured，不會在 import 時炸）
"""
from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any


class LLMError(RuntimeError):
    """呼叫失敗（網路、額度、模型拒答…）。呼叫端應退回「無法抽取，請人工輸入」。"""


class LLMNotConfigured(LLMError):
    """缺 key / model id。"""


@dataclass
class LLMResponse:
    text: str
    provider: str
    model: str
    usage: dict[str, Any] = field(default_factory=dict)
    raw: Any = None

    def json(self) -> Any:
        return parse_json_loose(self.text)


def parse_json_loose(text: str) -> Any:
    """模型回的 JSON 可能包在 ``` 裡或前後有話；抓第一個平衡的 {…} 或 […]。"""
    t = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", t, re.DOTALL)
    if m:
        t = m.group(1).strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    dec = json.JSONDecoder()
    for i, ch in enumerate(t):
        if ch in "{[":
            try:
                obj, _ = dec.raw_decode(t[i:])
                return obj
            except json.JSONDecodeError:
                continue
    raise LLMError(f"模型輸出不是 JSON：{t[:200]}")


class LLMProvider(ABC):
    name: str = "base"
    model: str = ""

    @abstractmethod
    def complete(self, prompt: str, *, images: Sequence[bytes] = (), system: str | None = None,
                 max_tokens: int = 16000) -> LLMResponse:
        """images = PNG bytes；放在文字前面送。"""

    def complete_json(self, prompt: str, **kw: Any) -> Any:
        return self.complete(prompt, **kw).json()

    def status(self) -> dict[str, Any]:
        return {"provider": self.name, "model": self.model, "configured": True}
