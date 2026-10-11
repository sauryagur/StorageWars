from conftest import auth, create_room, join_player


def test_report_requires_exactly_one_target_and_accepts_room_player(client):
    host = create_room(client)
    guest = join_player(client, host["roomCode"], "Guest player")
    neither = client.post(
        "/v1/reports", headers=auth(host["sessionToken"]), json={"reason": "OTHER"}
    )
    assert neither.status_code == 422
    assert neither.json()["code"] == "EXACTLY_ONE_TARGET"
    both = client.post(
        "/v1/reports",
        headers=auth(host["sessionToken"]),
        json={
            "reportedPlayerId": guest["playerId"],
            "reportedCardId": "00000000-0000-0000-0000-000000000001",
            "reason": "OTHER",
        },
    )
    assert both.status_code == 422
    valid = client.post(
        "/v1/reports",
        headers=auth(host["sessionToken"]),
        json={
            "reportedPlayerId": guest["playerId"],
            "reason": "AFK",
            "note": "Disconnected",
        },
    )
    assert valid.status_code == 202, valid.text
