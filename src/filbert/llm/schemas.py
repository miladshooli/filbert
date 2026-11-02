"""schemaهای آماده (pydantic) برای لایه LLM + بارگذاری schema دلخواه از فایل JSON Schema."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, create_model


class Entity(BaseModel):
    name: str = Field(description="نام موجودیت همان‌طور که در متن آمده")
    type: str = Field(description="person | organization | product | place | asset | other")


class ArticleFacts(BaseModel):
    """خلاصه و حقایق کلیدی یک مقاله/خبر فارسی."""

    summary_fa: str = Field(description="خلاصه ۲ تا ۳ جمله‌ای به فارسی روان")
    key_points: list[str] = Field(description="۳ تا ۷ نکته کلیدی، هر کدام یک جمله")
    entities: list[Entity] = Field(description="موجودیت‌های مهم نام‌برده‌شده")
    topics: list[str] = Field(description="۲ تا ۵ موضوع/برچسب کوتاه")
    tone: str = Field(
        description="news | analysis | tutorial | marketing | opinion | forum | other"
    )
    has_price_info: bool = Field(description="آیا متن قیمت/عدد مالی دارد")


class FaqItem(BaseModel):
    question: str
    answer: str


class SeoBrief(BaseModel):
    """پیشنهادهای سئو برای صفحه بر اساس محتوای اصلی."""

    suggested_title: str = Field(description="عنوان پیشنهادی ≤ ۶۰ کاراکتر، فارسی، شامل موضوع اصلی")
    suggested_description: str = Field(description="meta description پیشنهادی ۱۲۰ تا ۱۶۰ کاراکتر")
    primary_keyword: str
    secondary_keywords: list[str] = Field(description="۳ تا ۸ کلیدواژه فرعی")
    faq: list[FaqItem] = Field(description="۲ تا ۴ پرسش و پاسخ کوتاه قابل استفاده در FAQPage")
    content_gaps: list[str] = Field(description="نکاتی که محتوا جا انداخته یا باید کامل شود")


SCHEMAS: dict[str, type[BaseModel]] = {"article": ArticleFacts, "seo": SeoBrief}

_JSON_TYPES: dict[str, Any] = {"string": str, "integer": int, "number": float, "boolean": bool}


def _from_json_schema(name: str, schema: dict[str, Any]) -> type[BaseModel]:
    """تبدیل ساده JSON Schema (object با propertyهای اولیه/آرایه/شیء تودرتو) به مدل pydantic."""
    fields: dict[str, Any] = {}
    required = set(schema.get("required", []))
    for key, spec in (schema.get("properties") or {}).items():
        t = spec.get("type", "string")
        if t == "array":
            item = spec.get("items", {"type": "string"})
            inner = (
                _from_json_schema(f"{name}_{key}_item", item)
                if item.get("type") == "object"
                else _JSON_TYPES.get(item.get("type", "string"), str)
            )
            py: Any = list[inner]  # type: ignore[valid-type]
        elif t == "object":
            py = _from_json_schema(f"{name}_{key}", spec)
        else:
            py = _JSON_TYPES.get(t, str)
        default = ... if key in required else None
        if key not in required:
            py = py | None
        fields[key] = (py, Field(default, description=spec.get("description")))
    return create_model(name, **fields)  # type: ignore[call-overload]


def resolve_schema(spec: str) -> type[BaseModel]:
    """`article` | `seo` | مسیر فایل `.json` (JSON Schema)."""
    if spec in SCHEMAS:
        return SCHEMAS[spec]
    p = Path(spec)
    if p.suffix == ".json" and p.exists():
        data = json.loads(p.read_text(encoding="utf-8"))
        return _from_json_schema(p.stem.replace("-", "_") or "Custom", data)
    raise ValueError(f"unknown schema {spec!r}; use article|seo or a .json schema file")
