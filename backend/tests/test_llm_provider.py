import pytest

from app.llm import LLMNotConfigured, get_provider, parse_json_loose, provider_status
from app.llm.bedrock_provider import BedrockProvider
from app.llm.mock_provider import MockProvider


def test_env_switch(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    assert get_provider(response={"a": 1}).name == "mock"
    monkeypatch.setenv("LLM_PROVIDER", "bedrock")
    monkeypatch.delenv("BEDROCK_MODEL_ID", raising=False)
    p = get_provider(model="")
    assert isinstance(p, BedrockProvider) and p.status()["configured"] is False
    with pytest.raises(LLMNotConfigured):
        p.complete("hi")


def test_anthropic_without_key(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    st = provider_status()
    assert st["configured"] is False and "ANTHROPIC_API_KEY" in st["error"]


def test_unknown_provider():
    with pytest.raises(LLMNotConfigured):
        get_provider("gpt")


def test_mock_records_calls_and_json():
    p = MockProvider(response={"fields": {"x": {"value": 1, "confidence": 0.9}}})
    out = p.complete_json("讀這張表", images=[b"png"], system="sys")
    assert out["fields"]["x"]["value"] == 1
    assert p.calls[0]["n_images"] == 1


def test_parse_json_loose():
    assert parse_json_loose('好的，結果如下：\n```json\n{"a": [1,2]}\n```\n以上') == {"a": [1, 2]}
    assert parse_json_loose('前言 {"a": {"b": "}"}} 後語') == {"a": {"b": "}"}}


def test_bedrock_pacing_keeps_under_one_request_per_second(monkeypatch):
    from app.llm.bedrock_provider import BedrockProvider
    monkeypatch.setenv("BEDROCK_MIN_INTERVAL", "1.1")
    clock = {"t": 100.0}
    slept: list[float] = []
    def fake_sleep(sec):
        slept.append(sec); clock["t"] += sec
    BedrockProvider._last_call = 0.0
    assert BedrockProvider._pace(sleep=fake_sleep, now=lambda: clock["t"]) == 0.0      # 第一次不用等
    clock["t"] += 0.2
    w = BedrockProvider._pace(sleep=fake_sleep, now=lambda: clock["t"])                # 0.2 秒後再打 → 等 0.9
    assert abs(w - 0.9) < 1e-6 and slept == [w]
