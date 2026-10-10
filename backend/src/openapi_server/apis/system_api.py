# coding: utf-8

from typing import Dict, List  # noqa: F401
import importlib
import pkgutil

from openapi_server.apis.system_api_base import BaseSystemApi
import openapi_server.impl

from fastapi import (  # noqa: F401
    APIRouter,
    Body,
    Cookie,
    Depends,
    Form,
    Header,
    HTTPException,
    Path,
    Query,
    Response,
    Security,
    status,
)

from openapi_server.models.health_get200_response import HealthGet200Response

router = APIRouter()

ns_pkg = openapi_server.impl
for _, name, _ in pkgutil.iter_modules(ns_pkg.__path__, ns_pkg.__name__ + "."):
    importlib.import_module(name)


@router.get(
    "/health",
    responses={
        200: {"model": HealthGet200Response, "description": "OK"},
    },
    tags=["System"],
    summary="Liveness probe",
    response_model_by_alias=True,
)
async def health_get(
) -> HealthGet200Response:
    if not BaseSystemApi.subclasses:
        raise HTTPException(status_code=500, detail="Not implemented")
    return await BaseSystemApi.subclasses[0]().health_get()
