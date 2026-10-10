# coding: utf-8

from fastapi.testclient import TestClient


from pydantic import Field, field_validator  # noqa: F401
from typing import Any  # noqa: F401
from typing_extensions import Annotated  # noqa: F401
from openapi_server.models.error import Error  # noqa: F401
from openapi_server.models.inline_object1 import InlineObject1  # noqa: F401
from openapi_server.models.report_request import ReportRequest  # noqa: F401
from openapi_server.models.rooms_room_code_votekick_post200_response import RoomsRoomCodeVotekickPost200Response  # noqa: F401
from openapi_server.models.rooms_room_code_votekick_post_request import RoomsRoomCodeVotekickPostRequest  # noqa: F401


def test_reports_post(client: TestClient):
    """Test case for reports_post

    Report a card or a player
    """
    report_request = openapi_server.ReportRequest()

    headers = {
        "sessionToken": "special-key",
    }
    # uncomment below to make a request
    #response = client.request(
    #    "POST",
    #    "/reports",
    #    headers=headers,
    #    json=report_request,
    #)

    # uncomment below to assert the status code of the HTTP response
    #assert response.status_code == 200


def test_rooms_room_code_votekick_post(client: TestClient):
    """Test case for rooms_room_code_votekick_post

    Cast a votekick vote (idempotent)
    """
    rooms_room_code_votekick_post_request = openapi_server.RoomsRoomCodeVotekickPostRequest()

    headers = {
        "sessionToken": "special-key",
    }
    # uncomment below to make a request
    #response = client.request(
    #    "POST",
    #    "/rooms/{roomCode}/votekick".format(roomCode='room_code_example'),
    #    headers=headers,
    #    json=rooms_room_code_votekick_post_request,
    #)

    # uncomment below to assert the status code of the HTTP response
    #assert response.status_code == 200

