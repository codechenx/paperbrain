from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest

import paperbrain.adapters.parser_worker as parser_worker
from paperbrain.models import ParsedPaper


def test_worker_main_builds_parser_with_selected_backend_and_ocr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class FakeConnection:
        def __init__(self) -> None:
            self._commands = [("shutdown", None)]
            self.sent: list[tuple[str, Any]] = []
            self.closed = False

        def recv(self) -> tuple[str, Any]:
            return self._commands.pop(0)

        def send(self, payload: tuple[str, Any]) -> None:
            self.sent.append(payload)

        def close(self) -> None:
            self.closed = True

    class FakeParser:
        def create_converter(self) -> object:
            captured["create_converter"] = True
            return object()

        def parse_pdf_with_converter(self, path: Path, converter: object):  # noqa: ANN001, ANN201
            _ = (path, converter)
            raise AssertionError("parse should not run in this test")

    def fake_build_pdf_parser(pdf_parser: str, *, ocr_enabled: bool) -> object:
        captured["pdf_parser"] = pdf_parser
        captured["ocr_enabled"] = ocr_enabled
        return FakeParser()

    monkeypatch.setattr(parser_worker, "build_pdf_parser", fake_build_pdf_parser)
    connection = FakeConnection()

    parser_worker._worker_main(connection, parser_name="marker", ocr_enabled=True)

    assert captured["pdf_parser"] == "marker"
    assert captured["ocr_enabled"] is True
    assert captured["create_converter"] is True
    assert connection.sent == [("ready", None), ("ok", None)]
    assert connection.closed is True


def test_worker_main_parses_and_returns_payload(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_text("fake", encoding="utf-8")

    class FakeConnection:
        def __init__(self) -> None:
            self._commands = [("parse", str(pdf_path)), ("shutdown", None)]
            self.sent: list[tuple[str, Any]] = []

        def recv(self) -> tuple[str, Any]:
            return self._commands.pop(0)

        def send(self, payload: tuple[str, Any]) -> None:
            self.sent.append(payload)

        def close(self) -> None:
            return None

    class FakeParser:
        def create_converter(self) -> object:
            return object()

        def parse_pdf_with_converter(self, path: Path, converter: object) -> ParsedPaper:
            _ = converter
            assert path == pdf_path
            return ParsedPaper(
                title="t",
                journal="j",
                year=2024,
                authors=[],
                corresponding_authors=[],
                full_text="x",
                source_path=str(pdf_path),
            )

    monkeypatch.setattr(parser_worker, "build_pdf_parser", lambda *_args, **_kwargs: FakeParser())
    connection = FakeConnection()

    parser_worker._worker_main(connection, parser_name="docling", ocr_enabled=False)

    assert connection.sent[0] == ("ready", None)
    assert connection.sent[1][0] == "ok"
    payload = connection.sent[1][1]
    assert payload == asdict(
        ParsedPaper(
            title="t",
            journal="j",
            year=2024,
            authors=[],
            corresponding_authors=[],
            full_text="x",
            source_path=str(pdf_path),
        )
    )
    assert connection.sent[2] == ("ok", None)


def test_worker_main_falls_back_to_parse_pdf_for_non_converter_parser(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_text("fake", encoding="utf-8")
    captured: dict[str, Any] = {}

    class FakeConnection:
        def __init__(self) -> None:
            self._commands = [("parse", str(pdf_path)), ("shutdown", None)]
            self.sent: list[tuple[str, Any]] = []

        def recv(self) -> tuple[str, Any]:
            return self._commands.pop(0)

        def send(self, payload: tuple[str, Any]) -> None:
            self.sent.append(payload)

        def close(self) -> None:
            return None

    class BasicParser:
        def parse_pdf(self, path: Path) -> ParsedPaper:
            captured["path"] = path
            return ParsedPaper(
                title="basic",
                journal="j",
                year=2024,
                authors=[],
                corresponding_authors=[],
                full_text="x",
                source_path=str(path),
            )

    monkeypatch.setattr(parser_worker, "build_pdf_parser", lambda *_args, **_kwargs: BasicParser())
    connection = FakeConnection()

    parser_worker._worker_main(connection, parser_name="marker", ocr_enabled=False)

    assert captured["path"] == pdf_path
    assert connection.sent[0] == ("ready", None)
    assert connection.sent[1][0] == "ok"


def test_worker_main_does_not_create_converter_without_converter_parse_method(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_text("fake", encoding="utf-8")
    captured: dict[str, Any] = {}

    class FakeConnection:
        def __init__(self) -> None:
            self._commands = [("parse", str(pdf_path)), ("shutdown", None)]
            self.sent: list[tuple[str, Any]] = []

        def recv(self) -> tuple[str, Any]:
            return self._commands.pop(0)

        def send(self, payload: tuple[str, Any]) -> None:
            self.sent.append(payload)

        def close(self) -> None:
            return None

    class BasicParserWithConverterFactory:
        def create_converter(self) -> object:
            captured["create_converter"] = True
            return object()

        def parse_pdf(self, path: Path) -> ParsedPaper:
            captured["path"] = path
            return ParsedPaper(
                title="basic",
                journal="j",
                year=2024,
                authors=[],
                corresponding_authors=[],
                full_text="x",
                source_path=str(path),
            )

    monkeypatch.setattr(
        parser_worker, "build_pdf_parser", lambda *_args, **_kwargs: BasicParserWithConverterFactory()
    )
    connection = FakeConnection()

    parser_worker._worker_main(connection, parser_name="marker", ocr_enabled=False)

    assert captured["path"] == pdf_path
    assert "create_converter" not in captured
    assert connection.sent[0] == ("ready", None)
    assert connection.sent[1][0] == "ok"


def test_worker_main_surfaces_parse_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_text("fake", encoding="utf-8")

    class FakeConnection:
        def __init__(self) -> None:
            self._commands = [("parse", str(pdf_path)), ("shutdown", None)]
            self.sent: list[tuple[str, Any]] = []

        def recv(self) -> tuple[str, Any]:
            return self._commands.pop(0)

        def send(self, payload: tuple[str, Any]) -> None:
            self.sent.append(payload)

        def close(self) -> None:
            return None

    class BrokenParser:
        def create_converter(self) -> object:
            return object()

        def parse_pdf_with_converter(self, path: Path, converter: object):  # noqa: ANN001, ANN201
            _ = (path, converter)
            raise RuntimeError("boom")

    monkeypatch.setattr(parser_worker, "build_pdf_parser", lambda *_args, **_kwargs: BrokenParser())
    connection = FakeConnection()

    parser_worker._worker_main(connection, parser_name="marker", ocr_enabled=False)

    assert connection.sent[0] == ("ready", None)
    assert connection.sent[1][0] == "error"
    payload = connection.sent[1][1]
    assert str(pdf_path) in payload
    assert "RuntimeError: boom" in payload


def test_worker_main_surfaces_startup_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeConnection:
        def __init__(self) -> None:
            self.sent: list[tuple[str, Any]] = []
            self.closed = False

        def recv(self) -> tuple[str, Any]:
            raise AssertionError("recv should not be called on startup failure")

        def send(self, payload: tuple[str, Any]) -> None:
            self.sent.append(payload)

        def close(self) -> None:
            self.closed = True

    def fake_build_pdf_parser(*_args: Any, **_kwargs: Any) -> object:
        raise ValueError("invalid parser config")

    monkeypatch.setattr(parser_worker, "build_pdf_parser", fake_build_pdf_parser)
    connection = FakeConnection()

    parser_worker._worker_main(connection, parser_name="marker", ocr_enabled=False)

    assert connection.sent == [("error", "ValueError: invalid parser config")]
    assert connection.closed is True


def test_parser_parse_worker_parse_and_close(monkeypatch: pytest.MonkeyPatch) -> None:
    parsed = ParsedPaper(
        title="t",
        journal="j",
        year=2024,
        authors=[],
        corresponding_authors=[],
        full_text="x",
        source_path="/work/sample.pdf",
    )

    class FakeConnection:
        def __init__(self) -> None:
            self.sent: list[tuple[str, Any]] = []
            self._recv: list[tuple[str, Any]] = [("ready", None), ("ok", asdict(parsed)), ("ok", None)]
            self.closed = False

        def send(self, payload: tuple[str, Any]) -> None:
            self.sent.append(payload)

        def recv(self) -> tuple[str, Any]:
            return self._recv.pop(0)

        def close(self) -> None:
            self.closed = True

    class FakeProcess:
        def __init__(self, target: object, args: tuple[Any, ...]) -> None:
            _ = (target, args)
            self.started = False
            self.alive = True

        def start(self) -> None:
            self.started = True

        def is_alive(self) -> bool:
            return self.alive

        def join(self, timeout: int) -> None:
            _ = timeout
            self.alive = False

        def terminate(self) -> None:
            self.alive = False

    class FakeContext:
        def __init__(self) -> None:
            self.parent = FakeConnection()
            self.child = FakeConnection()
            self.process: FakeProcess | None = None

        def Pipe(self) -> tuple[FakeConnection, FakeConnection]:
            return self.parent, self.child

        def Process(self, target: object, args: tuple[Any, ...]) -> FakeProcess:
            self.process = FakeProcess(target, args)
            return self.process

    fake_context = FakeContext()
    monkeypatch.setattr(parser_worker, "get_context", lambda method: fake_context)

    worker = parser_worker.ParserParseWorker(parser_name="docling", ocr_enabled=False)
    result = worker.parse(Path("example.pdf"))
    worker.close()

    assert result == parsed
    assert fake_context.parent.sent == [("parse", "example.pdf"), ("shutdown", None)]
    assert fake_context.parent.closed is True
    assert fake_context.child.closed is True


def test_parser_parse_worker_init_surfaces_startup_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeConnection:
        def __init__(self) -> None:
            self._recv: list[tuple[str, Any]] = [("error", "ValueError: invalid parser config")]
            self.closed = False

        def send(self, payload: tuple[str, Any]) -> None:
            _ = payload

        def recv(self) -> tuple[str, Any]:
            return self._recv.pop(0)

        def close(self) -> None:
            self.closed = True

    class FakeProcess:
        def __init__(self, target: object, args: tuple[Any, ...]) -> None:
            _ = (target, args)
            self.alive = True
            self.started = False
            self.terminated = False

        def start(self) -> None:
            self.started = True

        def is_alive(self) -> bool:
            return self.alive

        def join(self, timeout: int) -> None:
            _ = timeout

        def terminate(self) -> None:
            self.terminated = True
            self.alive = False

    class FakeContext:
        def __init__(self) -> None:
            self.parent = FakeConnection()
            self.child = FakeConnection()
            self.process: FakeProcess | None = None

        def Pipe(self) -> tuple[FakeConnection, FakeConnection]:
            return self.parent, self.child

        def Process(self, target: object, args: tuple[Any, ...]) -> FakeProcess:
            self.process = FakeProcess(target, args)
            return self.process

    fake_context = FakeContext()
    monkeypatch.setattr(parser_worker, "get_context", lambda method: fake_context)

    with pytest.raises(RuntimeError, match="Failed to start parser worker 'marker': ValueError: invalid parser config"):
        parser_worker.ParserParseWorker(parser_name="marker", ocr_enabled=False)

    assert fake_context.parent.closed is True
    assert fake_context.child.closed is True
    assert fake_context.process is not None
    assert fake_context.process.terminated is True


def test_parser_parse_worker_wraps_parse_transport_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeConnection:
        def __init__(self) -> None:
            self._recv: list[tuple[str, Any]] = [("ready", None), ("ok", None)]
            self.closed = False
            self.sent: list[tuple[str, Any]] = []

        def send(self, payload: tuple[str, Any]) -> None:
            if payload[0] == "parse":
                raise ConnectionResetError("socket closed")
            self.sent.append(payload)

        def recv(self) -> tuple[str, Any]:
            return self._recv.pop(0)

        def close(self) -> None:
            self.closed = True

    class FakeProcess:
        def __init__(self, target: object, args: tuple[Any, ...]) -> None:
            _ = (target, args)
            self.alive = True

        def start(self) -> None:
            return None

        def is_alive(self) -> bool:
            return self.alive

        def join(self, timeout: int) -> None:
            _ = timeout
            self.alive = False

        def terminate(self) -> None:
            self.alive = False

    class FakeContext:
        def __init__(self) -> None:
            self.parent = FakeConnection()
            self.child = FakeConnection()

        def Pipe(self) -> tuple[FakeConnection, FakeConnection]:
            return self.parent, self.child

        def Process(self, target: object, args: tuple[Any, ...]) -> FakeProcess:
            return FakeProcess(target, args)

    fake_context = FakeContext()
    monkeypatch.setattr(parser_worker, "get_context", lambda method: fake_context)

    worker = parser_worker.ParserParseWorker(parser_name="marker", ocr_enabled=False)

    with pytest.raises(
        RuntimeError,
        match="Parser worker transport failure for 'marker' while parsing 'example.pdf': ConnectionResetError: socket closed",
    ):
        worker.parse(Path("example.pdf"))

    worker.close()
