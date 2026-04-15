from html import escape
from pathlib import Path
from typing import Callable, Generator, Literal

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request

from paperbrain.cli import DEFAULT_CONFIG_PATH
from paperbrain.config import ConfigStore
from paperbrain.web.repository import WebCardRepository

CardTypeParam = Literal["paper", "person", "topic"]
TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


def _is_htmx_request(request: Request) -> bool:
    return request.headers.get("HX-Request", "").lower() == "true"


def _render_htmx_error_fragment(message: str) -> str:
    return (
        '<div class="rounded border border-rose-300 bg-rose-50 px-3 py-2 text-sm text-rose-800">'
        f"{escape(message)}"
        "</div>"
    )

def get_web_repository() -> WebCardRepository:
    try:
        import psycopg
    except ModuleNotFoundError as exc:  # pragma: no cover - env guard
        raise RuntimeError("psycopg is required for web repository") from exc
    database_url = ConfigStore(DEFAULT_CONFIG_PATH).load().database_url
    connection = psycopg.connect(database_url, autocommit=True)
    repository = WebCardRepository(connection)
    setattr(repository, "_paperbrain_owned_connection", connection)
    return repository


def _build_default_repo_factory(config_path: Path) -> Callable[[], WebCardRepository]:
    try:
        import psycopg
    except ModuleNotFoundError as exc:  # pragma: no cover - env guard
        raise RuntimeError("psycopg is required for web repository") from exc

    def factory() -> WebCardRepository:
        database_url = ConfigStore(config_path).load().database_url
        connection = psycopg.connect(database_url, autocommit=True)
        repository = WebCardRepository(connection)
        setattr(repository, "_paperbrain_owned_connection", connection)
        return repository

    return factory


def _repository_dependency(repo_factory: Callable[[], WebCardRepository]) -> Generator[WebCardRepository, None, None]:
    repo = repo_factory()
    try:
        yield repo
    finally:
        connection = getattr(repo, "_paperbrain_owned_connection", None)
        if connection is not None:
            connection.close()


def create_app(
    repo_factory: Callable[[], WebCardRepository] | None = None,
    config_path: Path = DEFAULT_CONFIG_PATH,
) -> FastAPI:
    app = FastAPI(title="PaperBrain Browser")
    templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
    effective_repo_factory = repo_factory or _build_default_repo_factory(config_path)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> HTMLResponse:
        if not _is_htmx_request(request):
            return await request_validation_exception_handler(request, exc)
        return HTMLResponse(_render_htmx_error_fragment("Unable to load cards. Check filters and try again."), status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def htmx_http_exception_handler(request: Request, exc: StarletteHTTPException) -> HTMLResponse:
        if not _is_htmx_request(request) or exc.status_code not in {404, 422}:
            return await http_exception_handler(request, exc)
        message = exc.detail if isinstance(exc.detail, str) and exc.detail else "Not Found"
        return HTMLResponse(_render_htmx_error_fragment(message), status_code=exc.status_code)

    def get_request_repository() -> Generator[WebCardRepository, None, None]:
        yield from _repository_dependency(effective_repo_factory)

    @app.get("/", response_class=HTMLResponse)
    def homepage(
        request: Request,
        repo: WebCardRepository = Depends(get_request_repository),
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
            "append": False,
        }
        return templates.TemplateResponse(request, "index.html", context)

    @app.get("/cards", response_class=HTMLResponse)
    def cards_fragment(
        request: Request,
        repo: WebCardRepository = Depends(get_request_repository),
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
                "append": page > 1,
            },
        )

    @app.get("/cards/{card_type}/{card_id:path}", response_class=HTMLResponse)
    def card_detail(
        request: Request,
        card_type: CardTypeParam,
        card_id: str,
        repo: WebCardRepository = Depends(get_request_repository),
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

    return app


app = create_app()
