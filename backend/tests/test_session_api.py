# coding: utf-8

from fastapi.testclient import TestClient


from openapi_server.models.error import Error  # noqa: F401
from openapi_server.models.game_snapshot import GameSnapshot  # noqa: F401
from openapi_server.models.inline_object import InlineObject  # noqa: F401
from openapi_server.models.ws_ticket import WsTicket  # noqa: F401


def test_ws_ticket_post(client: TestClient):
    """Test case for ws_ticket_post

    Mint a single-use WebSocket ticket
    """

    headers = {
        "sessionToken": "special-key",
    }
    # uncomment below to make a request
    #response = client.request(
    #    "POST",
    #    "/ws/ticket",
    #    headers=headers,
    #)

    # uncomment below to assert the status code of the HTTP response
    #assert response.status_code == 200


def test_games_current_snapshot_get(client: TestClient):
    """Test case for games_current_snapshot_get

    Authoritative per-player state snapshot
    """

    headers = {
        "sessionToken": "special-key",
    }
    # uncomment below to make a request
    #response = client.request(
    #    "GET",
    #    "/games/current/snapshot",
    #    headers=headers,
    #)

    # uncomment below to assert the status code of the HTTP response
    #assert response.status_code == 200

