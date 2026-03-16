"""Offset-based pagination helpers.

Provides :class:`PaginationParams` for parsing query parameters and
:class:`PaginatedResponse` as a generic base for paginated list endpoints.
"""

from __future__ import annotations

from typing import Any

from fastapi import Query
from pydantic import BaseModel, Field

__all__ = [
    "PaginatedResponse",
    "PaginationParams",
    "pagination_query",
]


class PaginationParams(BaseModel):
    """Parsed pagination query parameters.

    Attributes:
        offset: Zero-based offset into the result set.
        limit: Maximum number of items to return.
    """

    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1)


def pagination_query(
    offset: int = Query(default=0, ge=0, description="Zero-based offset"),
    limit: int = Query(default=20, ge=1, description="Max items to return"),
) -> PaginationParams:
    """FastAPI dependency that extracts pagination from query params."""
    return PaginationParams(offset=offset, limit=limit)


class PaginatedResponse(BaseModel):
    """Generic base model for paginated list responses.

    Subclass and override ``items`` with a typed list for specific
    domain models.

    Attributes:
        items: Page of result items.
        total: Total count across all pages.
        offset: Offset used for this page.
        limit: Limit used for this page.
    """

    items: list[Any]
    total: int
    offset: int
    limit: int
