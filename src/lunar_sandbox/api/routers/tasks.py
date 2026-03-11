"""Task listing endpoints."""

from fastapi import APIRouter

router = APIRouter(prefix="/api/tasks", tags=["tasks"])
