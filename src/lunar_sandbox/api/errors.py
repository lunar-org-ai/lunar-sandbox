"""RFC 7807 Problem Details error handling.

Provides :class:`ProblemDetail` Pydantic model and exception handlers
that convert both :class:`HTTPException` and unhandled exceptions into
``application/problem+json`` responses per RFC 7807 / RFC 9457.

Hand-rolled instead of using ``fastapi-rfc7807`` (GPL, unmaintained).
"""

from __future__ import annotations

import structlog
from fastapi import Request
from fastapi.exceptions import HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

__all__ = [
    "ProblemDetail",
    "generic_exception_handler",
    "http_exception_handler",
]

logger = structlog.get_logger(__name__)


class ProblemDetail(BaseModel):
    """RFC 7807 Problem Details response body.

    Attributes:
        type: A URI reference identifying the problem type.
        title: Short, human-readable summary.
        status: HTTP status code.
        detail: Human-readable explanation specific to this occurrence.
    """

    type: str = "about:blank"
    title: str
    status: int
    detail: str


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Convert FastAPI HTTPException to RFC 7807 Problem Details response."""
    detail_str = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    body = ProblemDetail(
        title=detail_str,
        status=exc.status_code,
        detail=detail_str,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=body.model_dump(),
        media_type="application/problem+json",
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Convert unhandled exceptions to RFC 7807 Problem Details 500 response."""
    logger.error("unhandled_exception", error=str(exc), exc_info=exc)
    body = ProblemDetail(
        title="Internal Server Error",
        status=500,
        detail=str(exc),
    )
    return JSONResponse(
        status_code=500,
        content=body.model_dump(),
        media_type="application/problem+json",
    )
