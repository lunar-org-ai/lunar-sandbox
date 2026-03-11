"""Telemetry run endpoints."""

from fastapi import APIRouter

router = APIRouter(prefix="/api/telemetry", tags=["telemetry"])
