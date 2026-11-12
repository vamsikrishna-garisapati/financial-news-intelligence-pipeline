"""Shared API schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PaginationMeta(BaseModel):
    total: int
    limit: int
    offset: int


class PaginatedResponse[T](BaseModel):
    items: list[T]
    pagination: PaginationMeta


class MessageResponse(BaseModel):
    detail: str = Field(..., examples=["Not found"])
