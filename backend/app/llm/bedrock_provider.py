"""
Amazon Bedrock，走 boto3 bedrock-runtime 的 Converse API（各家模型共用的介面，當天不管開通的是哪個 Claude 版本都能用）。
BEDROCK_MODEL_ID 當天依開通結果填（例：anthropic.claude-opus-5 或 us.anthropic.… 的 inference profile）。
沒有 key / model id 時 import 與建構都不會炸，呼叫 complete() 才丟 LLMNotConfigured。
"""
from __future__ import annotations

import os
import threading
import time
from collections.abc import Sequence

from .base import LLMError, LLMNotConfigured, LLMProvider, LLMResponse


class BedrockProvider(LLMProvider):
    """黑客松競賽規範：Bedrock 請求須低於每秒 1 次。所有實例共用一個節拍器，兩次呼叫至少間隔 BEDROCK_MIN_INTERVAL 秒（預設 1.1）。"""
    name = "bedrock"
    _lock = threading.Lock()
    _last_call = 0.0

    @classmethod
    def _pace(cls, sleep=time.sleep, now=time.monotonic) -> float:
        """回傳實際等了幾秒。"""
        interval = float(os.environ.get("BEDROCK_MIN_INTERVAL", "1.1"))
        with cls._lock:
            wait = max(0.0, cls._last_call + interval - now())
            if wait > 0:
                sleep(wait)
            cls._last_call = now()
        return wait

    def __init__(self, model: str | None = None, region: str | None = None):
        self.model = model or os.environ.get("BEDROCK_MODEL_ID", "")
        self.region = region or os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"
        self._client = None

    def _ensure(self):
        if not self.model:
            raise LLMNotConfigured("缺 BEDROCK_MODEL_ID（當天依 Bedrock 開通結果填）")
        if self._client is None:
            try:
                import boto3
                from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError
            except ImportError as e:  # pragma: no cover
                raise LLMNotConfigured("未安裝 boto3：pip install -e '.[llm]'") from e
            self._exc = (BotoCoreError, ClientError)
            self._nocred = NoCredentialsError
            from botocore.config import Config
            # 逾時與重試上限：沒設的話一次卡住可等好幾分鐘（連線 10 秒、讀取 120 秒、最多重試 2 次）
            self._client = boto3.client("bedrock-runtime", region_name=self.region,
                                        config=Config(connect_timeout=10, read_timeout=120, retries={"max_attempts": 2}))
        return self._client

    def status(self) -> dict:
        return {"provider": self.name, "model": self.model, "region": self.region, "configured": bool(self.model)}

    def complete(self, prompt: str, *, images: Sequence[bytes] = (), system: str | None = None,
                 max_tokens: int = 16000) -> LLMResponse:
        client = self._ensure()
        content: list[dict] = [{"image": {"format": "png", "source": {"bytes": img}}} for img in images]
        content.append({"text": prompt})
        kwargs: dict = {"modelId": self.model, "messages": [{"role": "user", "content": content}],
                        "inferenceConfig": {"maxTokens": max_tokens}}
        if system:
            kwargs["system"] = [{"text": system}]
        self._pace()                                          # 規範：< 1 RPS
        try:
            resp = client.converse(**kwargs)
        except self._nocred as e:
            raise LLMNotConfigured(f"沒有 AWS 憑證：{e}") from e
        except self._exc as e:
            raise LLMError(f"Bedrock 呼叫失敗：{e}") from e
        parts = resp.get("output", {}).get("message", {}).get("content", [])
        text = "".join(p.get("text", "") for p in parts if "text" in p)
        usage = resp.get("usage", {})
        return LLMResponse(text=text, provider=self.name, model=self.model, usage=usage, raw=resp)
