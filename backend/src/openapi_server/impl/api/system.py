from __future__ import annotations

from fastapi.responses import JSONResponse

from openapi_server.apis.system_api_base import BaseSystemApi
from openapi_server.models.health_get200_response import HealthGet200Response


class SystemApiImpl(BaseSystemApi):
    async def health_get(self) -> JSONResponse:
        body = HealthGet200Response(status="ok")
        return JSONResponse(
            body.model_dump(by_alias=True, exclude_unset=True, mode="json"),
            status_code=200,
        )
