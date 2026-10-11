from __future__ import annotations

import secrets

from fastapi import Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.security.api_key import APIKeyHeader

from openapi_server.impl.config import settings
from openapi_server.impl.context import SessionContext, current_admin, current_session
from openapi_server.impl.errors import AdminUnauthorized, ApiError
from openapi_server.impl.engine.registry import registry
from openapi_server.impl.tables import hash_session_token
from openapi_server.models.extra_models import TokenModel


async def get_token_sessionToken(
    request: Request,
    token_api_key_header: str | None = Security(
        APIKeyHeader(name="X-Session-Token", auto_error=False)
    ),
) -> TokenModel:
    if not token_api_key_header:
        raise ApiError(401, "UNAUTHORIZED", "Missing or invalid session token.")
    identity = registry.resolve(token_api_key_header)
    if identity is None:
        raise ApiError(401, "UNAUTHORIZED", "Missing or invalid session token.")
    room, player = identity
    requested_code = request.path_params.get("roomCode")
    if requested_code and requested_code.upper() != room.code.upper():
        raise ApiError(403, "WRONG_ROOM", "Session token belongs to another room.")
    current_session.set(SessionContext(room.id, room.code, player.id, hash_session_token(token_api_key_header)))
    return TokenModel(sub=player.id)


async def get_token_adminAuth(
    credentials: HTTPAuthorizationCredentials | None = Security(HTTPBearer(auto_error=False)),
) -> TokenModel:
    current_admin.set(False)
    token = credentials.credentials if credentials is not None else ""
    if not settings.admin_token or not secrets.compare_digest(token, settings.admin_token):
        raise AdminUnauthorized()
    current_admin.set(True)
    return TokenModel(sub="admin")
