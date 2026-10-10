# coding: utf-8

from fastapi.testclient import TestClient


from typing import Any  # noqa: F401
from openapi_server.models.error import Error  # noqa: F401
from openapi_server.models.inline_object import InlineObject  # noqa: F401
from openapi_server.models.reveal_slide import RevealSlide  # noqa: F401


def test_games_current_reveal_get(client: TestClient):
    """Test case for games_current_reveal_get

    Current reveal slide
    """

    headers = {
        "sessionToken": "special-key",
    }
    # uncomment below to make a request
    #response = client.request(
    #    "GET",
    #    "/games/current/reveal",
    #    headers=headers,
    #)

    # uncomment below to assert the status code of the HTTP response
    #assert response.status_code == 200


def test_games_current_reveal_advance_post(client: TestClient):
    """Test case for games_current_reveal_advance_post

    Advance the carousel early (creator only)
    """

    headers = {
        "sessionToken": "special-key",
    }
    # uncomment below to make a request
    #response = client.request(
    #    "POST",
    #    "/games/current/reveal/advance",
    #    headers=headers,
    #)

    # uncomment below to assert the status code of the HTTP response
    #assert response.status_code == 200

