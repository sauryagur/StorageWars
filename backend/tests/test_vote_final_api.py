# coding: utf-8

from fastapi.testclient import TestClient


from pydantic import Field, field_validator  # noqa: F401
from typing import Any  # noqa: F401
from typing_extensions import Annotated  # noqa: F401
from openapi_server.models.error import Error  # noqa: F401
from openapi_server.models.final_scoreboard import FinalScoreboard  # noqa: F401
from openapi_server.models.games_current_vote_post_request import GamesCurrentVotePostRequest  # noqa: F401
from openapi_server.models.inline_object import InlineObject  # noqa: F401
from openapi_server.models.replay_response import ReplayResponse  # noqa: F401
from openapi_server.models.vote_options import VoteOptions  # noqa: F401


def test_rooms_room_code_replay_post(client: TestClient):
    """Test case for rooms_room_code_replay_post

    Create a replay room (creator only, FINAL phase only)
    """

    headers = {
        "sessionToken": "special-key",
    }
    # uncomment below to make a request
    #response = client.request(
    #    "POST",
    #    "/rooms/{roomCode}/replay".format(roomCode='room_code_example'),
    #    headers=headers,
    #)

    # uncomment below to assert the status code of the HTTP response
    #assert response.status_code == 200


def test_games_current_vote_options_get(client: TestClient):
    """Test case for games_current_vote_options_get

    Cards eligible for my funniest-card vote
    """

    headers = {
        "sessionToken": "special-key",
    }
    # uncomment below to make a request
    #response = client.request(
    #    "GET",
    #    "/games/current/vote/options",
    #    headers=headers,
    #)

    # uncomment below to assert the status code of the HTTP response
    #assert response.status_code == 200


def test_games_current_vote_post(client: TestClient):
    """Test case for games_current_vote_post

    Cast funniest-card vote (one, final)
    """
    games_current_vote_post_request = openapi_server.GamesCurrentVotePostRequest()

    headers = {
        "sessionToken": "special-key",
    }
    # uncomment below to make a request
    #response = client.request(
    #    "POST",
    #    "/games/current/vote",
    #    headers=headers,
    #    json=games_current_vote_post_request,
    #)

    # uncomment below to assert the status code of the HTTP response
    #assert response.status_code == 200


def test_games_current_final_get(client: TestClient):
    """Test case for games_current_final_get

    Final scoreboard
    """

    headers = {
        "sessionToken": "special-key",
    }
    # uncomment below to make a request
    #response = client.request(
    #    "GET",
    #    "/games/current/final",
    #    headers=headers,
    #)

    # uncomment below to assert the status code of the HTTP response
    #assert response.status_code == 200

