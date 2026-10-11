from conftest import auth, create_room, join_player


def run_pre_reveal_http_responses_without_product_secrets(client, clock):
    host = create_room(client)
    players = [host] + [
        join_player(client, host["roomCode"], f"Player {index}")
        for index in range(2, 5)
    ]
    start = client.post(
        f"/v1/rooms/{host['roomCode']}/start", headers=auth(host["sessionToken"])
    )
    assert start.status_code == 202
    from openapi_server.impl.engine.registry import registry

    room = registry.get_by_code(host["roomCode"])
    image_url_fragment = "/media/products/"
    bodies = []
    bodies.append(
        client.get(
            f"/v1/rooms/{host['roomCode']}", headers=auth(host["sessionToken"])
        ).text
    )
    bodies.append(
        client.get(
            "/v1/games/current/snapshot", headers=auth(host["sessionToken"])
        ).text
    )
    own_card = client.get(
        "/v1/games/current/author-card", headers=auth(host["sessionToken"])
    )
    assert own_card.status_code == 200
    author_body = own_card.json()
    assert image_url_fragment in author_body["imageUrl"]
    from urllib.parse import urlsplit

    signed_image = urlsplit(author_body["imageUrl"])
    image = client.get(f"{signed_image.path}?{signed_image.query}")
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/png"
    assert image.content.startswith(b"\x89PNG\r\n\x1a\n")
    bodies.append(own_card.text.replace(author_body["imageUrl"], ""))
    titles = [
        "Safe item for cooking",
        "Safe item for gardening",
        "Safe item for travel",
        "Safe item for work",
    ]
    for title, player in zip(titles, players):
        response = client.put(
            "/v1/games/current/author-card",
            headers=auth(player["sessionToken"]),
            json={"title": title, "category": "home-kitchen"},
        )
        assert response.status_code == 200
        bodies.append(response.text)
    for player in players:
        queue = client.get(
            "/v1/games/current/guess/queue", headers=auth(player["sessionToken"])
        )
        assert queue.status_code == 200
        bodies.append(queue.text)
    target_guesser = players[1]
    target_queue = client.get(
        "/v1/games/current/guess/queue", headers=auth(target_guesser["sessionToken"])
    ).json()["cards"]
    card_id = target_queue[0]["cardId"]
    target = room.cards[__import__("uuid").UUID(card_id).hex]
    protected = [
        str(target.product.price_cents),
        target.product.original_title,
        target.product.original_description,
    ]
    opened = client.post(
        f"/v1/games/current/guess/cards/{card_id}/open",
        headers=auth(target_guesser["sessionToken"]),
    )
    assert opened.status_code == 200
    bodies.append(opened.text)
    draft = client.put(
        f"/v1/games/current/guess/cards/{card_id}/draft",
        headers=auth(target_guesser["sessionToken"]),
        json={"valueCents": 5000},
    )
    assert draft.status_code == 200
    bodies.append(draft.text)
    error = client.post(
        f"/v1/games/current/guess/cards/{card_id}/lock",
        headers=auth(target_guesser["sessionToken"]),
        json={"valueCents": 5000},
    )
    assert error.status_code == 403
    bodies.append(error.text)
    assert (
        client.post(
            f"/v1/games/current/guess/cards/{card_id}/touch",
            headers=auth(target_guesser["sessionToken"]),
        ).status_code
        == 204
    )
    ticket = client.post("/v1/ws/ticket", headers=auth(target_guesser["sessionToken"]))
    assert ticket.status_code == 201
    with client.websocket_connect(
        f"/v1/ws/{host['roomCode']}?ticket={ticket.json()['ticket']}"
    ) as websocket:
        hello = websocket.receive_json()
        assert hello["type"] == "hello"
        clock.advance(3)
        locked = client.post(
            f"/v1/games/current/guess/cards/{card_id}/lock",
            headers=auth(target_guesser["sessionToken"]),
            json={"valueCents": 5000},
        )
        assert locked.status_code == 200
        bodies.append(locked.text)
        frames = [websocket.receive_json(), websocket.receive_json()]
        assert {frame["type"] for frame in frames} == {
            "player_presence",
            "lock_confirmed",
        }
        for frame in frames:
            body = __import__("json").dumps(frame)
            for secret in protected:
                assert secret not in body
            assert image_url_fragment not in body
    for body in bodies:
        for secret in protected:
            assert secret not in body
        assert image_url_fragment not in body
