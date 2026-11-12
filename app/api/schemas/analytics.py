"""Analytics response schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class NewsVolumeResponse(BaseModel):
    group_by: Literal["company", "date", "source"]
    items: list[dict[str, Any]] = Field(default_factory=list)


class CategoryVolumeItem(BaseModel):
    category: str
    count: int


class CategoryVolumeResponse(BaseModel):
    items: list[CategoryVolumeItem]
    note: str = (
        "Categories are rule-based pipeline labels for analytics only. "
        "They are not investment recommendations."
    )
