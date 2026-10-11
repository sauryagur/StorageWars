from conftest import auth, create_room


def test_reveal_and_final_are_phase_guarded(client):
    host = create_room(client)
    reveal = client.get("/v1/games/current/reveal", headers=auth(host["sessionToken"]))
    assert reveal.status_code == 409
    assert reveal.json()["code"] == "WRONG_PHASE"
    assert reveal.json()["phase"] == "LOBBY"
    final = client.get("/v1/games/current/final", headers=auth(host["sessionToken"]))
    assert final.status_code == 409
    assert final.json()["code"] == "WRONG_PHASE"
