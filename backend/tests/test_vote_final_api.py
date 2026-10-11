from conftest import auth, create_room


def test_vote_and_replay_reject_wrong_phase(client):
    host = create_room(client)
    options = client.get(
        "/v1/games/current/vote/options", headers=auth(host["sessionToken"])
    )
    assert options.status_code == 409
    assert options.json()["code"] == "WRONG_PHASE"
    replay = client.post(
        f"/v1/rooms/{host['roomCode']}/replay", headers=auth(host["sessionToken"])
    )
    assert replay.status_code == 409
    assert replay.json()["code"] == "WRONG_PHASE"
