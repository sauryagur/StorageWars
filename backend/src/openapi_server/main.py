from __future__ import annotations

from contextlib import asynccontextmanager

import json

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from openapi_server.apis.admin_api import router as AdminApiRouter
from openapi_server.apis.author_api import router as AuthorApiRouter
from openapi_server.apis.guess_api import router as GuessApiRouter
from openapi_server.apis.moderation_api import router as ModerationApiRouter
from openapi_server.apis.reveal_api import router as RevealApiRouter
from openapi_server.apis.rooms_api import router as RoomsApiRouter
from openapi_server.apis.session_api import router as SessionApiRouter
from openapi_server.apis.system_api import router as SystemApiRouter
from openapi_server.apis.vote_final_api import router as VoteFinalApiRouter
from openapi_server.impl.config import settings
from openapi_server.impl.engine.registry import registry
from openapi_server.impl.errors import install_exception_handlers
from openapi_server.security_api import get_token_adminAuth


@asynccontextmanager
async def lifespan(app: FastAPI):
    from openapi_server.impl.db import init_db
    from openapi_server.impl.content import seed_reference_data
    from openapi_server.impl.engine.registry import registry

    await init_db()
    await seed_reference_data()
    if settings.seed_fixtures:
        from openapi_server.impl.ingest import seed_fixtures
        await seed_fixtures()
    if settings.serverless:
        # Functions have no long-lived tasks: requests drive the clock instead
        # (see `tick_all` in the request middleware below).
        app.state.room_sweeper = None
    else:
        app.state.room_sweeper = registry.start_sweeper()
    try:
        yield
    finally:
        if app.state.room_sweeper is not None:
            app.state.room_sweeper.cancel()


app = FastAPI(title="Impulse Buy API", version="2.0.0", lifespan=lifespan)
from openapi_server.impl.context import client_ip


@app.middleware("http")
async def bind_request_context(request: Request, call_next):
    token = client_ip.set(request.client.host if request.client else "unknown")
    try:
        if settings.serverless:
            await registry.tick_all()
        # OpenAPI Generator's oneOf request wrapper is not deserialized by
        # Pydantic when FastAPI binds it, so adapt the documented raw body to
        # its `actual_instance` field before validation.
        if request.method == "POST" and request.url.path.startswith("/v1/rooms/") and request.url.path.endswith("/join"):
            try:
                body = await request.json()
            except (json.JSONDecodeError, UnicodeDecodeError):
                body = None
            if isinstance(body, dict) and "actual_instance" not in body and ("name" in body or "sessionToken" in body):
                request._body = json.dumps({"actual_instance": body}).encode()
                sent = False

                async def receive():
                    nonlocal sent
                    if not sent:
                        sent = True
                        return {"type": "http.request", "body": request._body, "more_body": False}
                    return {"type": "http.request", "body": b"", "more_body": False}

                request._receive = receive
        return await call_next(request)
    finally:
        client_ip.reset(token)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_allow_origins),
    allow_headers=["Content-Type", "X-Session-Token", "Authorization"],
    allow_methods=["*"],
)
install_exception_handlers(app)

for router in (AdminApiRouter, AuthorApiRouter, GuessApiRouter, ModerationApiRouter,
               RevealApiRouter, RoomsApiRouter, SessionApiRouter, SystemApiRouter,
               VoteFinalApiRouter):
    app.include_router(router, prefix="/v1")

from openapi_server.impl.media import media_route
app.add_api_route("/media/products/{key:path}", media_route, methods=["GET"], include_in_schema=False)
from openapi_server.impl.realtime import ws_endpoint
app.add_api_websocket_route("/v1/ws/{roomCode}", ws_endpoint)


async def system_tick() -> dict[str, int]:
    """Advance every live room and expire stale ones.

    Not part of the published contract: Vercel Cron (or any scheduler) calls it
    so rooms, seats and rejoin windows are collected while nobody is polling.
    """
    await registry.tick_all()
    return {"rooms": len(registry.rooms), "expired": len(registry.sweep())}


app.add_api_route(
    "/v1/system/tick",
    system_tick,
    methods=["POST"],
    dependencies=[Depends(get_token_adminAuth)],
    include_in_schema=False,
)
