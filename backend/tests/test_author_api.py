from conftest import auth, create_room, join_player


def test_author_drip_fields_are_omitted_until_stage_and_blank_is_null(client, clock):
    host = create_room(client)
    players = [host] + [
        join_player(client, host["roomCode"], f"Author {index}")
        for index in range(2, 5)
    ]
    response = client.post(
        f"/v1/rooms/{host['roomCode']}/start", headers=auth(host["sessionToken"])
    )
    assert response.status_code == 202, response.text
    titles = [
        "Useful item for cooking",
        "Useful item for gardening",
        "Useful item for travel",
        "Useful item for work",
    ]
    for title, player in zip(titles, players):
        submitted = client.put(
            "/v1/games/current/author-card",
            headers=auth(player["sessionToken"]),
            json={"title": title, "category": "home-kitchen"},
        )
        assert submitted.status_code == 200, submitted.text
    from openapi_server.impl.engine.registry import registry

    room = registry.get_by_code(host["roomCode"])
    guesser = players[1]
    queue = client.get(
        "/v1/games/current/guess/queue", headers=auth(guesser["sessionToken"])
    )
    assert queue.status_code == 200
    queue_item = queue.json()["cards"][0]
    card = room.cards[__import__("uuid").UUID(queue_item["cardId"]).hex]
    opened = client.post(
        f"/v1/games/current/guess/cards/{queue_item['cardId']}/open",
        headers=auth(guesser["sessionToken"]),
    )
    assert opened.status_code == 200
    assert opened.json()["title"] == card.title
    assert opened.json()["category"] == "home-kitchen"
    assert "bullets" not in opened.json()
    assert "starRating" not in opened.json()
    clock.advance(4)
    room.async_tick()
    at_four = client.get(
        f"/v1/games/current/guess/cards/{card.id}",
        headers=auth(guesser["sessionToken"]),
    ).json()
    assert "bullets" not in at_four
    assert "starRating" not in at_four
    clock.advance(1)
    room.async_tick()
    at_five = client.get(
        f"/v1/games/current/guess/cards/{card.id}",
        headers=auth(guesser["sessionToken"]),
    ).json()
    assert at_five["bullets"] is None
    assert "starRating" not in at_five
    clock.advance(5)
    room.async_tick()
    at_ten = client.get(
        f"/v1/games/current/guess/cards/{card.id}",
        headers=auth(guesser["sessionToken"]),
    ).json()
    assert at_ten["bullets"] is None
    assert at_ten["starRating"] is None
    assert at_ten["reviewBucket"] is None
