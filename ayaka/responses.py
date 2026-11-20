"""Consistent JSON envelope for every response."""
from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from fastapi.responses import JSONResponse


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [jsonable(v) for v in value]
    if isinstance(value, dt.datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=dt.timezone.utc)
        return value.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, Decimal):
        return float(value)
    return value


def ok(data: Any = None, message: str = "Request successful", status: int = 200,
       headers: dict | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"success": True, "message": message,
                 "data": jsonable(data if data is not None else {}),
                 "timestamp": now_iso()},
        headers=headers,
    )


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str,
                 details: Any = None, headers: dict | None = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details
        self.headers = headers or {}


def error_response(status: int, code: str, message: str, details: Any = None,
                   headers: dict | None = None) -> JSONResponse:
    err: dict[str, Any] = {"code": code}
    if details is not None:
        err["details"] = jsonable(details)
    return JSONResponse(
        status_code=status,
        content={"success": False, "message": message, "error": err, "timestamp": now_iso()},
        headers=headers,
    )
