from typing import Any

import pytest

import paperbrain.adapters.docling_worker as docling_worker


@pytest.mark.parametrize("ocr_enabled", [False, True])
def test_worker_main_constructs_docling_parser_with_ocr_toggle(
    monkeypatch: pytest.MonkeyPatch, ocr_enabled: bool
) -> None:
    captured: dict[str, Any] = {}

    class FakeConnection:
        def __init__(self) -> None:
            self.sent: list[tuple[str, Any]] = []
            self.closed = False
            self._commands = [("shutdown", None)]

        def recv(self) -> tuple[str, Any]:
            return self._commands.pop(0)

        def send(self, payload: tuple[str, Any]) -> None:
            self.sent.append(payload)

        def close(self) -> None:
            self.closed = True

    class FakeParser:
        def __init__(self, *, ocr_enabled: bool = False) -> None:
            captured["ocr_enabled"] = ocr_enabled

        def create_converter(self) -> object:
            return object()

    monkeypatch.setattr(docling_worker, "DoclingParser", FakeParser)

    connection = FakeConnection()
    docling_worker._worker_main(connection, ocr_enabled)

    assert captured["ocr_enabled"] is ocr_enabled
    assert connection.sent == [("ok", None)]
    assert connection.closed is True
