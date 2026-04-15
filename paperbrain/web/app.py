from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from paperbrain.cli import DEFAULT_CONFIG_PATH
from paperbrain.config import ConfigStore
from paperbrain.web.repository import WebCardRepository

CardTypeParam = Literal["paper", "person", "topic"]
TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"

_repository: WebCardRepository | None = None
_connection: Any = None


@lru_cache(maxsize=1)
def _load_database_url() -> str:
    return ConfigStore(DEFAULT_CONFIG_PATH).load().database_url


def get_web_repository() -> WebCardRepository:
    global _repository, _connection
    if _repository is None:
        try:
            import psycopg
        except ModuleNotFoundError as exc:  # pragma: no cover - env guard
            raise RuntimeError("psycopg is required for web repository") from exc
        _connection = psycopg.connect(_load_database_url(), autocommit=False)
        _repository = WebCardRepository(_connection)
    return _repository


def create_app() -> FastAPI:
    app = FastAPI(title="PaperBrain Browser")
    templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

    @app.get("/", response_class=HTMLResponse)
    def homepage(
        request: Request,
        repo: WebCardRepository = Depends(get_web_repository),
        q: str = Query(default="", max_length=500),
        card_type: CardTypeParam = Query(default="paper"),
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=24, ge=1, le=100),
    ) -> HTMLResponse:
        cards, has_more = repo.list_cards(card_type=card_type, query=q, page=page, page_size=page_size)
        context = {
            "request": request,
            "cards": cards,
            "card_type": card_type,
            "q": q,
            "page": page,
            "page_size": page_size,
            "has_more": has_more,
        }
        return templates.TemplateResponse(request, "index.html", context)

    @app.get("/cards", response_class=HTMLResponse)
    def cards_fragment(
        request: Request,
        repo: WebCardRepository = Depends(get_web_repository),
        q: str = Query(default="", max_length=500),
        card_type: CardTypeParam = Query(default="paper"),
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=24, ge=1, le=100),
    ) -> HTMLResponse:
        cards, has_more = repo.list_cards(card_type=card_type, query=q, page=page, page_size=page_size)
        return templates.TemplateResponse(
            request,
            "_card_grid.html",
            {
                "request": request,
                "cards": cards,
                "card_type": card_type,
                "q": q,
                "page": page,
                "page_size": page_size,
                "has_more": has_more,
            },
        )

    @app.get("/cards/{card_type}/{card_id:path}", response_class=HTMLResponse)
    def card_detail(
        request: Request,
        card_type: CardTypeParam,
        card_id: str,
        repo: WebCardRepository = Depends(get_web_repository),
    ) -> HTMLResponse:
        card = repo.get_card(card_type=card_type, slug=card_id)
        if card is None:
            raise HTTPException(status_code=404, detail="Card not found")
        return templates.TemplateResponse(
            request,
            "_detail_panel.html",
            {
                "request": request,
                "card": card,
                "card_type": card_type,
            },
        )

    @app.on_event("shutdown")
    def close_repository_connection() -> None:
        global _connection, _repository
        if _connection is not None:
            _connection.close()
            _connection = None
            _repository = None

    return app


app = create_app()
