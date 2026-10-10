# coding: utf-8

from fastapi.testclient import TestClient


from pydantic import Field, field_validator  # noqa: F401
from typing_extensions import Annotated  # noqa: F401
from openapi_server.models.error import Error  # noqa: F401
from openapi_server.models.inline_object1 import InlineObject1  # noqa: F401
from openapi_server.models.join_response import JoinResponse  # noqa: F401
from openapi_server.models.room_state import RoomState  # noqa: F401
from openapi_server.models.rooms_post_request import RoomsPostRequest  # noqa: F401
from openapi_server.models.rooms_room_code_join_post_request import RoomsRoomCodeJoinPostRequest  # noqa: F401
from openapi_server.models.rooms_room_code_start_post202_response import RoomsRoomCodeStartPost202Response  # noqa: F401


def test_rooms_post(client: TestClient):
    """Test case for rooms_post

    Create a room and join as creator
    """
    rooms_post_request = openapi_server.RoomsPostRequest()

    headers = {
    }
    # uncomment below to make a request
    #response = client.request(
    #    "POST",
    #    "/rooms",
    #    headers=headers,
    #    json=rooms_post_request,
    #)

    # uncomment below to assert the status code of the HTTP response
    #assert response.status_code == 200


def test_rooms_room_code_join_post(client: TestClient):
    """Test case for rooms_room_code_join_post

    Join a room, or rejoin an existing seat
    """
    rooms_room_code_join_post_request = openapi_server.RoomsRoomCodeJoinPostRequest()

    headers = {
    }
    # uncomment below to make a request
    #response = client.request(
    #    "POST",
    #    "/rooms/{roomCode}/join".format(roomCode='room_code_example'),
    #    headers=headers,
    #    json=rooms_room_code_join_post_request,
    #)

    # uncomment below to assert the status code of the HTTP response
    #assert response.status_code == 200


def test_rooms_room_code_get(client: TestClient):
    """Test case for rooms_room_code_get

    Room / lobby state
    """

    headers = {
        "sessionToken": "special-key",
    }
    # uncomment below to make a request
    #response = client.request(
    #    "GET",
    #    "/rooms/{roomCode}".format(roomCode='room_code_example'),
    #    headers=headers,
    #)

    # uncomment below to assert the status code of the HTTP response
    #assert response.status_code == 200


def test_rooms_room_code_start_post(client: TestClient):
    """Test case for rooms_room_code_start_post

    Start the game (creator only)
    """

    headers = {
        "sessionToken": "special-key",
    }
    # uncomment below to make a request
    #response = client.request(
    #    "POST",
    #    "/rooms/{roomCode}/start".format(roomCode='room_code_example'),
    #    headers=headers,
    #)

    # uncomment below to assert the status code of the HTTP response
    #assert response.status_code == 200

