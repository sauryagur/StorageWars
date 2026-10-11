from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response

SESSION_401_EMPTY_BODY = True


class ApiError(Exception):
    def __init__(
        self,
        status: int,
        code: str,
        message: str = "",
        *,
        phase: str | None = None,
        retry_in_phase: str | None = None,
        field_errors: list[dict[str, Any]] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status, self.code, self.message = status, code, message
        self.phase, self.retry_in_phase = phase, retry_in_phase
        self.field_errors, self.headers = field_errors, headers or {}
        super().__init__(message or code)


class AdminUnauthorized(Exception):
    pass


def require_session():
    from openapi_server.impl.context import current_session

    try:
        return current_session.get()
    except LookupError as exc:
        raise RuntimeError("session context is not set") from exc


def require_admin() -> None:
    from openapi_server.impl.context import current_admin

    try:
        if current_admin.get():
            return
    except LookupError:
        pass
    raise AdminUnauthorized()


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
        if exc.status == 401 and exc.code == "UNAUTHORIZED" and SESSION_401_EMPTY_BODY:
            return Response(status_code=401, headers=exc.headers)
        body: dict[str, Any] = {"code": exc.code, "message": exc.message or exc.code}
        if exc.phase is not None:
            body["phase"] = exc.phase
        retry_in_phase = exc.retry_in_phase
        if exc.code == "WRONG_PHASE" and retry_in_phase is None:
            path = request.url.path
            retry_in_phase = (
                "AUTHOR"
                if "/author-card" in path
                else (
                    "GUESS"
                    if "/guess/" in path
                    else (
                        "REVEAL"
                        if "/reveal" in path
                        else (
                            "VOTE"
                            if "/vote" in path
                            else (
                                "FINAL"
                                if path.endswith(("/final", "/replay"))
                                else None
                            )
                        )
                    )
                )
            )
        if retry_in_phase is not None:
            body["retryInPhase"] = retry_in_phase
        if exc.field_errors is not None:
            body["fieldErrors"] = exc.field_errors
        return JSONResponse(body, status_code=exc.status, headers=exc.headers)

    @app.exception_handler(AdminUnauthorized)
    async def admin_unauthorized_handler(
        request: Request, exc: AdminUnauthorized
    ) -> Response:
        return Response(status_code=401)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        author = "/author-card" in request.url.path
        value_input = request.url.path.endswith(("/draft", "/lock"))
        errors = []
        for error in exc.errors():
            loc = tuple(error.get("loc", ()))
            field = ".".join(str(part) for part in loc[1:])
            error_type = error.get("type", "")
            if "starRating" in field and error_type == "multiple_of":
                rule = "STAR_RATING_STEP"
            elif "category" in field and error_type == "enum":
                rule = "CATEGORY_UNKNOWN"
            elif error_type == "string_too_short":
                rule = "TOO_SHORT"
            elif error_type == "string_too_long":
                rule = "TOO_LONG"
            elif error_type in (
                "greater_than",
                "greater_than_equal",
                "less_than",
                "less_than_equal",
            ):
                rule = "OUT_OF_RANGE"
            else:
                rule = "VALIDATION_FAILED"
            errors.append(
                {
                    "field": field,
                    "rule": rule,
                    "message": error.get("msg", "Invalid value"),
                }
            )
        if value_input:
            return JSONResponse(
                {"code": "VALUE_NOT_NUMERIC", "message": "Value must be an integer."},
                status_code=422,
            )
        code = "VALIDATION_FAILED"
        message = (
            "Author card validation failed." if author else "Request validation failed."
        )
        return JSONResponse(
            {"code": code, "message": message, "fieldErrors": errors}, status_code=422
        )
