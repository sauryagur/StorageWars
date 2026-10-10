# coding: utf-8

from fastapi.testclient import TestClient


from typing import Any  # noqa: F401
from uuid import UUID  # noqa: F401
from openapi_server.models.error import Error  # noqa: F401
from openapi_server.models.guess_card_view import GuessCardView  # noqa: F401
from openapi_server.models.guess_queue import GuessQueue  # noqa: F401
from openapi_server.models.inline_object import InlineObject  # noqa: F401
from openapi_server.models.lock_response import LockResponse  # noqa: F401
from openapi_server.models.value_echo import ValueEcho  # noqa: F401
from openapi_server.models.value_input import ValueInput  # noqa: F401


def test_games_current_guess_queue_get(client: TestClient):
    """Test case for games_current_guess_queue_get

    My shuffled card queue
    """

    headers = {
        "sessionToken": "special-key",
    }
    # uncomment below to make a request
    #response = client.request(
    #    "GET",
    #    "/games/current/guess/queue",
    #    headers=headers,
    #)

    # uncomment below to assert the status code of the HTTP response
    #assert response.status_code == 200


def test_games_current_guess_cards_card_id_open_post(client: TestClient):
    """Test case for games_current_guess_cards_card_id_open_post

    Open the next card (starts its drip schedule)
    """

    headers = {
        "sessionToken": "special-key",
    }
    # uncomment below to make a request
    #response = client.request(
    #    "POST",
    #    "/games/current/guess/cards/{cardId}/open".format(cardId=UUID('38400000-8cf0-11bd-b23e-10b96e4ef00d')),
    #    headers=headers,
    #)

    # uncomment below to assert the status code of the HTTP response
    #assert response.status_code == 200


def test_games_current_guess_cards_card_id_get(client: TestClient):
    """Test case for games_current_guess_cards_card_id_get

    Read my active card (drip-redacted, read-only)
    """

    headers = {
        "sessionToken": "special-key",
    }
    # uncomment below to make a request
    #response = client.request(
    #    "GET",
    #    "/games/current/guess/cards/{cardId}".format(cardId=UUID('38400000-8cf0-11bd-b23e-10b96e4ef00d')),
    #    headers=headers,
    #)

    # uncomment below to assert the status code of the HTTP response
    #assert response.status_code == 200


def test_games_current_guess_cards_card_id_draft_put(client: TestClient):
    """Test case for games_current_guess_cards_card_id_draft_put

    Update the server-side draft value (the slider position)
    """
    value_input = openapi_server.ValueInput()

    headers = {
        "sessionToken": "special-key",
    }
    # uncomment below to make a request
    #response = client.request(
    #    "PUT",
    #    "/games/current/guess/cards/{cardId}/draft".format(cardId=UUID('38400000-8cf0-11bd-b23e-10b96e4ef00d')),
    #    headers=headers,
    #    json=value_input,
    #)

    # uncomment below to assert the status code of the HTTP response
    #assert response.status_code == 200


def test_games_current_guess_cards_card_id_touch_post(client: TestClient):
    """Test case for games_current_guess_cards_card_id_touch_post

    Report slider touched (enables Lock)
    """

    headers = {
        "sessionToken": "special-key",
    }
    # uncomment below to make a request
    #response = client.request(
    #    "POST",
    #    "/games/current/guess/cards/{cardId}/touch".format(cardId=UUID('38400000-8cf0-11bd-b23e-10b96e4ef00d')),
    #    headers=headers,
    #)

    # uncomment below to assert the status code of the HTTP response
    #assert response.status_code == 200


def test_games_current_guess_cards_card_id_lock_post(client: TestClient):
    """Test case for games_current_guess_cards_card_id_lock_post

    Lock my guess (permanent)
    """
    value_input = openapi_server.ValueInput()

    headers = {
        "sessionToken": "special-key",
    }
    # uncomment below to make a request
    #response = client.request(
    #    "POST",
    #    "/games/current/guess/cards/{cardId}/lock".format(cardId=UUID('38400000-8cf0-11bd-b23e-10b96e4ef00d')),
    #    headers=headers,
    #    json=value_input,
    #)

    # uncomment below to assert the status code of the HTTP response
    #assert response.status_code == 200

