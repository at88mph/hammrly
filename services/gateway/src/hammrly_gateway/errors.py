from __future__ import annotations

from typing import Any, Optional

from fastapi.responses import JSONResponse


def problem(
    status_code: int,
    *,
    error: str,
    message: str,
    details: Optional[dict[str, Any]] = None,
) -> JSONResponse:
    body: dict[str, Any] = {"error": error, "message": message}
    if details:
        body["details"] = details
    return JSONResponse(status_code=status_code, content=body)
