from conftest import auth, create_room, join_player
from openapi_server.impl.ratelimit import limiter


def test_session_auth_wrong_room_unknown_token_and_create_rate_limit(client):
    host = create_room(client)
    other = create_room(client, "Other")
    wrong_room = client.get(
        f"/v1/rooms/{other['roomCode']}", headers=auth(host["sessionToken"])
    )
    assert wrong_room.status_code == 403
    assert wrong_room.json()["code"] == "WRONG_ROOM"
    unknown = client.get(
        f"/v1/rooms/{host['roomCode']}", headers=auth("not-a-session-token")
    )
    assert unknown.status_code == 401
    assert unknown.content == b""
    limiter.reset()
    for index in range(10):
        assert (
            client.post("/v1/rooms", json={"name": f"Guest {index}"}).status_code == 201
        )
    limited = client.post("/v1/rooms", json={"name": "Final Guest"})
    assert limited.status_code == 429
    assert limited.json()["code"] == "RATE_LIMITED"
    assert int(limited.headers["Retry-After"]) >= 1


def begin_four_player_game(client):
    host = create_room(client)
    players = [host] + [
        join_player(client, host["roomCode"], f"Player {i}") for i in range(2, 5)
    ]
    started = client.post(
        f"/v1/rooms/{host['roomCode']}/start", headers=auth(host["sessionToken"])
    )
    assert started.status_code == 202, started.text
    titles = [
        "Useful item for cooking",
        "Useful item for gardening",
        "Useful item for travel",
        "Useful item for work",
    ]
    for title, player in zip(titles, players):
        saved = client.put(
            "/v1/games/current/author-card",
            headers=auth(player["sessionToken"]),
            json={
                "title": title,
                "bullets": ["A genuinely useful feature description"],
                "starRating": 4.5,
                "reviewBucket": "TEN_TO_99",
                "category": "home-kitchen",
            },
        )
        assert saved.status_code == 200, saved.text
    return host, players


def run_http_game_and_replay_claim_use_original_tokens(client, clock):
    host, players = begin_four_player_game(client)
    room_code = host["roomCode"]
    room = client.get(f"/v1/rooms/{room_code}", headers=auth(host["sessionToken"]))
    assert room.status_code == 200 and room.json()["phase"] == "GUESS"
    for player in players:
        headers = auth(player["sessionToken"])
        queue_response = client.get("/v1/games/current/guess/queue", headers=headers)
        assert queue_response.status_code == 200
        for item in queue_response.json()["cards"]:
            card_id = item["cardId"]
            opened = client.post(
                f"/v1/games/current/guess/cards/{card_id}/open", headers=headers
            )
            assert opened.status_code == 200, opened.text
            assert "priceCents" not in opened.json()
            draft = client.put(
                f"/v1/games/current/guess/cards/{card_id}/draft",
                headers=headers,
                json={"valueCents": 5000},
            )
            assert draft.status_code == 200
            assert (
                client.post(
                    f"/v1/games/current/guess/cards/{card_id}/touch", headers=headers
                ).status_code
                == 204
            )
            clock.advance(3)
            locked = client.post(
                f"/v1/games/current/guess/cards/{card_id}/lock",
                headers=headers,
                json={"valueCents": 5000},
            )
            assert locked.status_code == 200, locked.text
            assert "points" not in locked.json()
    from openapi_server.impl.engine.registry import registry

    room_engine = registry.get_by_code(room_code)
    assert room_engine.phase.value == "REVEAL"
    while room_engine.phase.value == "REVEAL":
        advanced = client.post(
            "/v1/games/current/reveal/advance", headers=auth(host["sessionToken"])
        )
        assert advanced.status_code == 202, advanced.text
    assert room_engine.phase.value == "VOTE"
    for player in players:
        options = client.get(
            "/v1/games/current/vote/options", headers=auth(player["sessionToken"])
        )
        assert options.status_code == 200
        choices = options.json()["options"]
        assert choices
        voted = client.post(
            "/v1/games/current/vote",
            headers=auth(player["sessionToken"]),
            json={"cardId": choices[0]["cardId"]},
        )
        assert voted.status_code == 202, voted.text
    final = client.get("/v1/games/current/final", headers=auth(host["sessionToken"]))
    assert final.status_code == 200, final.text
    for row in final.json()["rankings"]:
        assert row["totalPoints"] == sum(row["breakdown"].values())
    maxima = [
        row
        for row in final.json()["rankings"]
        if row["totalPoints"]
        == max(item["totalPoints"] for item in final.json()["rankings"])
    ]
    assert final.json().get("winnerPlayerId") == (
        maxima[0]["playerId"] if len(maxima) == 1 else None
    )
    replay = client.post(
        f"/v1/rooms/{room_code}/replay", headers=auth(host["sessionToken"])
    )
    assert replay.status_code == 201, replay.text
    replay_code = replay.json()["newRoomCode"]
    for player in players:
        claim = client.post(
            f"/v1/rooms/{replay_code}/join",
            json={"sessionToken": player["sessionToken"]},
        )
        assert claim.status_code == 200, claim.text
        assert claim.json()["sessionToken"] == player["sessionToken"]
