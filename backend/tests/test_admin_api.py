import pytest

from dataclasses import replace

from conftest import auth, create_room


def _admin_headers():
    return {"Authorization": "Bearer test-admin-secret"}


def test_admin_auth_product_filters_unknown_image_and_report_resolution(
    client, monkeypatch
):
    from openapi_server import security_api
    from openapi_server.impl import content
    from openapi_server.impl.config import settings

    denied = client.get(
        "/v1/admin/products", headers={"Authorization": "Bearer player-token"}
    )
    assert denied.status_code == 401
    assert denied.content == b""
    monkeypatch.setattr(
        security_api, "settings", replace(settings, admin_token="test-admin-secret")
    )
    headers = _admin_headers()
    products = client.get("/v1/admin/products", headers=headers)
    assert products.status_code == 200 and len(products.json()) >= 24
    first = products.json()[0]
    band_filter = client.get(
        f"/v1/admin/products?priceBand={first['priceBand']}", headers=headers
    )
    assert band_filter.status_code == 200 and band_filter.json()
    assert all(item["priceBand"] == first["priceBand"] for item in band_filter.json())
    active_filter = client.get(
        "/v1/admin/products?active=true&category=home-kitchen", headers=headers
    )
    assert active_filter.status_code == 200
    assert all(
        item["active"] is True and item["category"] == "home-kitchen"
        for item in active_filter.json()
    )

    unknown_image = client.post(
        "/v1/admin/products",
        headers=headers,
        json={
            "imageStorageKey": "products/not-registered.webp",
            "originalTitle": "Admin-created product",
            "originalDescription": "A test catalog entry.",
            "priceCents": 5999,
            "currency": "USD",
            "category": "home-kitchen",
            "snapshotDate": "2026-01-01",
        },
    )
    assert unknown_image.status_code == 422
    assert unknown_image.json()["code"] == "IMAGE_KEY_UNKNOWN"

    room = create_room(client)
    report = client.post(
        "/v1/reports",
        headers=auth(room["sessionToken"]),
        json={
            "reportedPlayerId": room["playerId"],
            "reason": "OTHER",
            "note": "Review this report",
        },
    )
    assert report.status_code == 202, report.text
    opened = client.get("/v1/admin/reports?status=OPEN", headers=headers)
    assert opened.status_code == 200 and len(opened.json()) == 1
    row = opened.json()[0]
    resolved = client.patch(
        f"/v1/admin/reports/{row['id']}",
        headers=headers,
        json={
            "status": "RESOLVED",
            "resolutionNote": "Reviewed and resolved",
        },
    )
    assert resolved.status_code == 200, resolved.text
    resolved_list = client.get("/v1/admin/reports?status=RESOLVED", headers=headers)
    assert len(resolved_list.json()) == 1
    assert resolved_list.json()[0]["resolutionNote"] == "Reviewed and resolved"

    import asyncio
    import math
    from types import SimpleNamespace
    from openapi_server.impl.engine.registry import registry
    from openapi_server.impl.engine.room import Guess

    product = SimpleNamespace(
        price_cents=10_000,
        category=SimpleNamespace(slug="home-kitchen", sigma=0.5),
    )
    active_room, creator, _ = registry.create_room("Active Room")
    active_room.add_player("Active Guest")
    active_room.add_player("Another Guest")
    active_room.add_player("Last Guest")
    active_room.start([product, product, product, product], creator.id)
    active_card = next(iter(active_room.cards.values()))

    patch = client.patch(
        "/v1/admin/categories/home-kitchen", headers=headers, json={"sigma": 0.8}
    )
    assert patch.status_code == 200, patch.text
    assert active_card.product.category.sigma == 0.8
    guess = Guess(creator.id, value_cents=round(product.price_cents * math.exp(0.25)))
    active_room._score_guess(guess, active_card)
    assert guess.z == pytest.approx(
        abs(math.log(guess.value_cents / product.price_cents)) / 0.8
    )
    categories = asyncio.run(content.load_categories())
    assert next(item for item in categories if item.slug == "home-kitchen").sigma == 0.8
