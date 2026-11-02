import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from filbert.llm import ArticleFacts, LLMExtractor, LLMUnavailable, SeoBrief, resolve_schema


class FakeMessages:
    def __init__(self, payload: dict, stop_reason: str = "end_turn") -> None:
        self.payload = payload
        self.stop_reason = stop_reason
        self.calls: list[dict] = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        schema = kwargs["output_format"]
        parsed = None if self.stop_reason == "refusal" else schema.model_validate(self.payload)
        return SimpleNamespace(
            parsed_output=parsed,
            stop_reason=self.stop_reason,
            stop_details=SimpleNamespace(category="cyber"),
            usage=SimpleNamespace(input_tokens=120, output_tokens=40),
        )


def fake_client(payload: dict, stop_reason: str = "end_turn") -> SimpleNamespace:
    return SimpleNamespace(messages=FakeMessages(payload, stop_reason))


ARTICLE = {
    "summary_fa": "بیت‌کوین رشد کرد.",
    "key_points": ["رشد ۴ درصدی", "تقاضای نهادی"],
    "entities": [{"name": "بیت‌کوین", "type": "asset"}],
    "topics": ["رمزارز"],
    "tone": "news",
    "has_price_info": True,
}


def test_extract_uses_parse_and_caches(tmp_path: Path) -> None:
    client = fake_client(ARTICLE)
    ex = LLMExtractor(cache_dir=tmp_path, client=client)
    out = ex.extract("# تیتر\n\nمتن", ArticleFacts, url="https://a.ir/x")
    assert isinstance(out, ArticleFacts) and out.summary_fa == "بیت‌کوین رشد کرد."
    call = client.messages.calls[0]
    assert call["model"] == "claude-opus-5-5" and call["output_format"] is ArticleFacts
    assert call["system"][0]["cache_control"] == {"type": "ephemeral"} and call[
        "output_config"
    ] == {"effort": "medium"}
    assert (
        "<content>" in call["messages"][0]["content"]
        and "URL: https://a.ir/x" in call["messages"][0]["content"]
    )
    # دومین فراخوانی با همان ورودی از کش دیسک
    out2 = ex.extract("# تیتر\n\nمتن", ArticleFacts, url="https://a.ir/x")
    assert out2 == out and ex.stats == {
        "calls": 1,
        "cache_hits": 1,
        "input_tokens": 120,
        "output_tokens": 40,
    }
    assert len(list((tmp_path / "llm").glob("*.json"))) == 1


def test_refusal_raises() -> None:
    ex = LLMExtractor(client=fake_client(ARTICLE, stop_reason="refusal"))
    with pytest.raises(LLMUnavailable):
        ex.extract("متن", ArticleFacts)


def test_resolve_schema_builtin_and_json(tmp_path: Path) -> None:
    assert resolve_schema("article") is ArticleFacts and resolve_schema("seo") is SeoBrief
    schema = {
        "type": "object",
        "required": ["price"],
        "properties": {
            "price": {"type": "number", "description": "قیمت"},
            "tags": {"type": "array", "items": {"type": "string"}},
            "shop": {"type": "object", "properties": {"name": {"type": "string"}}},
        },
    }
    p = tmp_path / "product-facts.json"
    p.write_text(json.dumps(schema), encoding="utf-8")
    cls = resolve_schema(str(p))
    obj = cls.model_validate({"price": 12.5, "tags": ["a"], "shop": {"name": "x"}})
    assert obj.price == 12.5 and obj.tags == ["a"] and obj.shop.name == "x"
    assert cls.model_validate({"price": 1}).tags is None
    with pytest.raises(ValueError):
        resolve_schema("nope")


def test_truncation_warning(tmp_path: Path, caplog) -> None:
    client = fake_client(ARTICLE)
    ex = LLMExtractor(client=client)
    with caplog.at_level("WARNING"):
        ex.extract("x" * 70_000, ArticleFacts)
    assert (
        "truncated" in caplog.text
        and len(client.messages.calls[0]["messages"][0]["content"]) < 61_000
    )
