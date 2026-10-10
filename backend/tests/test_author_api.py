# coding: utf-8

from fastapi.testclient import TestClient


from openapi_server.models.author_card_stored import AuthorCardStored  # noqa: F401
from openapi_server.models.author_card_submission import AuthorCardSubmission  # noqa: F401
from openapi_server.models.author_card_view import AuthorCardView  # noqa: F401
from openapi_server.models.author_validation_error import AuthorValidationError  # noqa: F401
from openapi_server.models.inline_object import InlineObject  # noqa: F401


def test_games_current_author_card_get(client: TestClient):
    """Test case for games_current_author_card_get

    Get my card to author
    """

    headers = {
        "sessionToken": "special-key",
    }
    # uncomment below to make a request
    #response = client.request(
    #    "GET",
    #    "/games/current/author-card",
    #    headers=headers,
    #)

    # uncomment below to assert the status code of the HTTP response
    #assert response.status_code == 200


def test_games_current_author_card_put(client: TestClient):
    """Test case for games_current_author_card_put

    Submit my authored card (full or partial)
    """
    author_card_submission = openapi_server.AuthorCardSubmission()

    headers = {
        "sessionToken": "special-key",
    }
    # uncomment below to make a request
    #response = client.request(
    #    "PUT",
    #    "/games/current/author-card",
    #    headers=headers,
    #    json=author_card_submission,
    #)

    # uncomment below to assert the status code of the HTTP response
    #assert response.status_code == 200

