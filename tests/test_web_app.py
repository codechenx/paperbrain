import re
from importlib import import_module
from typing import Any

import pytest


class FakeWebCardRepository:
    def __init__(self) -> None:
        self.has_more = False
        self.cards = [
            {
                "slug": "paper-1",
                "entity_type": "paper",
                "title": "Paper One",
                "body": {"title": "Paper One"},
            }
        ]
        self.list_cards_calls: list[dict[str, Any]] = []
        self.get_card_calls: list[dict[str, str]] = []

    def list_cards(self, card_type: str, query: str, page: int, page_size: int) -> tuple[list[dict[str, Any]], bool]:
        self.list_cards_calls.append(
            {"card_type": card_type, "query": query, "page": page, "page_size": page_size}
        )
        return self.cards, self.has_more

    def get_card(self, card_type: str, slug: str) -> dict[str, Any] | None:
        self.get_card_calls.append({"card_type": card_type, "slug": slug})
        for card in self.cards:
            if card["slug"] == slug:
                return card
        return None


def _import_web_app_or_skip() -> Any:
    try:
        return import_module("paperbrain.web.app")
    except ModuleNotFoundError as exc:
        if exc.name in {"paperbrain.web", "paperbrain.web.app"}:
            pytest.fail(f"Route contract checks require paperbrain.web.app to exist (red-phase guard): {exc}")
        raise


def _build_client(monkeypatch: pytest.MonkeyPatch) -> tuple[Any, FakeWebCardRepository]:
    web_app = _import_web_app_or_skip()
    fake_repo = FakeWebCardRepository()

    if hasattr(web_app, "create_app"):
        try:
            app = web_app.create_app(repo_factory=lambda: fake_repo)
        except TypeError:
            if hasattr(web_app, "get_web_repository"):
                monkeypatch.setattr(web_app, "get_web_repository", lambda: fake_repo)
                app = web_app.create_app()
            elif hasattr(web_app, "WebCardRepository") and hasattr(web_app, "connect"):
                monkeypatch.setattr(web_app, "WebCardRepository", lambda _connection: fake_repo)
                monkeypatch.setattr(web_app, "connect", lambda *_args, **_kwargs: None)
                app = web_app.create_app()
            else:
                pytest.fail(
                    "Expected create_app(repo_factory=...) or legacy repository seam for route tests"
                )
    elif hasattr(web_app, "app"):
        app = web_app.app
    else:
        pytest.fail("Expected paperbrain.web.app to expose create_app() or app")

    try:
        from fastapi.testclient import TestClient
    except ModuleNotFoundError as exc:  # pragma: no cover - environment issue guard
        pytest.fail(f"Expected fastapi.testclient to be available for route tests: {exc}")

    return TestClient(app), fake_repo


def test_web_app_module_is_importable() -> None:
    import_module("paperbrain.web.app")



def test_create_app_uses_repo_factory_per_request() -> None:
    web_app = _import_web_app_or_skip()
    first_repo = FakeWebCardRepository()
    second_repo = FakeWebCardRepository()
    repos = [first_repo, second_repo]
    factory_calls = 0

    def repo_factory() -> FakeWebCardRepository:
        nonlocal factory_calls
        repo = repos[factory_calls]
        factory_calls += 1
        return repo

    app = web_app.create_app(repo_factory=repo_factory)

    from fastapi.testclient import TestClient

    client = TestClient(app)
    first = client.get('/')
    second = client.get('/cards', params={'card_type': 'paper', 'page': 1})

    assert first.status_code == 200
    assert second.status_code == 200
    assert factory_calls == 2
    assert len(first_repo.list_cards_calls) == 1
    assert len(second_repo.list_cards_calls) == 1


def test_cards_fragment_includes_infinite_scroll_loader_with_next_page(monkeypatch: pytest.MonkeyPatch) -> None:
    client, fake_repo = _build_client(monkeypatch)
    fake_repo.has_more = True

    response = client.get('/cards', params={'card_type': 'paper', 'q': 'genomics', 'page': 2, 'page_size': 24})

    assert response.status_code == 200
    body = response.text
    assert re.search(r"hx-trigger=[\"']revealed[\"']", body)
    assert re.search(r"hx-get=[\"']/cards\?[^\"']*card_type=paper", body)
    assert re.search(r"hx-get=[\"']/cards\?[^\"']*q=genomics", body)
    assert re.search(r"hx-get=[\"']/cards\?[^\"']*page=3", body)
    assert re.search(r"hx-get=[\"']/cards\?[^\"']*page_size=24", body)

def test_homepage_renders_tab_wiring_search_and_card_grid(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = _build_client(monkeypatch)

    response = client.get("/")

    assert response.status_code == 200
    body = response.text
    assert 'id="card-grid"' in body
    assert re.search(r'hx-get=["\']/cards\?[^"\']*card_type=paper', body)
    assert re.search(r'hx-get=["\']/cards\?[^"\']*card_type=person', body)
    assert re.search(r'hx-get=["\']/cards\?[^"\']*card_type=topic', body)
    assert re.search(r'<input[^>]+id=["\']active-card-type["\'][^>]+name=["\']card_type["\']', body)
    assert "hx-on::after-request=\"document.getElementById('active-card-type').value='paper'\"" in body
    assert "hx-on::after-request=\"document.getElementById('active-card-type').value='person'\"" in body
    assert "hx-on::after-request=\"document.getElementById('active-card-type').value='topic'\"" in body
    assert re.search(r'<input[^>]+name=["\']q["\']', body)


def test_cards_endpoint_returns_grid_fragment_with_detail_route_hx_get(monkeypatch: pytest.MonkeyPatch) -> None:
    client, fake_repo = _build_client(monkeypatch)

    response = client.get("/cards", params={"card_type": "paper", "q": "genomics", "page": 1})

    assert response.status_code == 200
    body = response.text
    assert 'id="card-grid"' in body
    assert re.search(r'hx-get=["\']/cards/paper/paper-1["\']', body)
    assert fake_repo.list_cards_calls == [
        {"card_type": "paper", "query": "genomics", "page": 1, "page_size": 24}
    ]


def test_card_detail_returns_200_and_rendered_content_for_existing_card(monkeypatch: pytest.MonkeyPatch) -> None:
    client, fake_repo = _build_client(monkeypatch)

    response = client.get("/cards/paper/paper-1")

    assert response.status_code == 200
    body = response.text
    assert "Paper One" in body
    assert fake_repo.get_card_calls == [{"card_type": "paper", "slug": "paper-1"}]


def test_card_detail_returns_404_for_missing_card(monkeypatch: pytest.MonkeyPatch) -> None:
    client, fake_repo = _build_client(monkeypatch)

    response = client.get("/cards/paper/missing-card")

    assert response.status_code == 404
    assert fake_repo.get_card_calls == [{"card_type": "paper", "slug": "missing-card"}]
