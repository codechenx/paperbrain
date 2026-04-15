from importlib import import_module
from typing import Any

import pytest


class FakeWebCardRepository:
    def __init__(self) -> None:
        self.cards = [
            {
                "slug": "paper-1",
                "entity_type": "paper",
                "title": "Paper One",
                "body": {"title": "Paper One"},
            }
        ]

    def list_cards(self, card_type: str, query: str, page: int, page_size: int) -> tuple[list[dict[str, Any]], bool]:
        del card_type, query, page, page_size
        return self.cards, False

    def get_card(self, card_type: str, slug: str) -> dict[str, Any] | None:
        del card_type
        for card in self.cards:
            if card["slug"] == slug:
                return card
        return None


def _build_client(monkeypatch: pytest.MonkeyPatch) -> Any:
    try:
        web_app = import_module("paperbrain.web.app")
    except ModuleNotFoundError as exc:  # pragma: no cover - this should fail until Task 4
        pytest.fail(f"Expected paperbrain.web.app to exist for FastAPI routes: {exc}")

    fake_repo = FakeWebCardRepository()

    if hasattr(web_app, "get_web_repository"):
        monkeypatch.setattr(web_app, "get_web_repository", lambda: fake_repo, raising=False)

    if hasattr(web_app, "WebCardRepository"):
        monkeypatch.setattr(web_app, "WebCardRepository", lambda _connection: fake_repo, raising=False)

    if hasattr(web_app, "connect"):
        monkeypatch.setattr(web_app, "connect", lambda *_args, **_kwargs: None, raising=False)

    if hasattr(web_app, "create_app"):
        app = web_app.create_app()
    elif hasattr(web_app, "app"):
        app = web_app.app
    else:  # pragma: no cover - intentional test guard
        pytest.fail("Expected paperbrain.web.app to expose create_app() or app")

    try:
        from fastapi.testclient import TestClient
    except ModuleNotFoundError as exc:  # pragma: no cover - environment issue guard
        pytest.fail(f"Expected fastapi.testclient to be available for route tests: {exc}")

    return TestClient(app)


def test_homepage_renders_tabs_search_and_card_grid(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _build_client(monkeypatch)

    response = client.get("/")

    assert response.status_code == 200
    body = response.text
    assert "Paper" in body
    assert "Person" in body
    assert "Topic" in body
    assert "<input" in body
    assert 'id="card-grid"' in body


def test_cards_endpoint_returns_grid_fragment_with_detail_hx_get(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _build_client(monkeypatch)

    response = client.get("/cards", params={"card_type": "paper", "q": "genomics", "page": 1})

    assert response.status_code == 200
    body = response.text
    assert 'id="card-grid"' in body
    assert '/cards/paper/paper-1' in body
    assert "hx-get" in body


def test_card_detail_returns_404_for_missing_card(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _build_client(monkeypatch)

    response = client.get("/cards/paper/missing-card")

    assert response.status_code == 404
