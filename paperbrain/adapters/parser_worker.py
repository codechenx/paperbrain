from __future__ import annotations

from dataclasses import asdict
from multiprocessing import get_context
from multiprocessing.connection import Connection
from pathlib import Path
from typing import Any

from paperbrain.adapters.parser_factory import build_pdf_parser
from paperbrain.models import ParsedPaper


def _worker_main(connection: Connection, parser_name: str, ocr_enabled: bool) -> None:
    parser = build_pdf_parser(parser_name, ocr_enabled=ocr_enabled)
    use_converter = hasattr(parser, "create_converter") and hasattr(
        parser, "parse_pdf_with_converter"
    )
    converter = parser.create_converter() if use_converter else None
    try:
        while True:
            command, payload = connection.recv()
            if command == "shutdown":
                connection.send(("ok", None))
                return
            if command != "parse":
                connection.send(("error", f"Unknown command: {command}"))
                continue
            try:
                file_path = Path(str(payload))
                if converter is not None:
                    parsed = parser.parse_pdf_with_converter(file_path, converter)
                else:
                    parsed = parser.parse_pdf(file_path)
            except Exception as exc:
                connection.send(("error", f"{file_path}: {type(exc).__name__}: {exc}"))
                continue
            connection.send(("ok", asdict(parsed)))
    finally:
        connection.close()


class ParserParseWorker:
    def __init__(self, *, parser_name: str, ocr_enabled: bool = False) -> None:
        context = get_context("spawn")
        parent_connection, child_connection = context.Pipe()
        self._connection = parent_connection
        self._process = context.Process(
            target=_worker_main, args=(child_connection, parser_name, ocr_enabled)
        )
        self._process.start()
        child_connection.close()

    def parse(self, path: Path) -> ParsedPaper:
        if not self._process.is_alive():
            raise RuntimeError("Parser worker process is not running")
        self._connection.send(("parse", str(path)))
        status, payload = self._connection.recv()
        if status != "ok":
            raise RuntimeError(str(payload))
        if not isinstance(payload, dict):
            raise RuntimeError("Parser worker returned an invalid payload")
        return ParsedPaper(**payload)

    def close(self) -> None:
        if self._process.is_alive():
            try:
                self._connection.send(("shutdown", None))
                self._connection.recv()
            except Exception:
                pass
            self._process.join(timeout=2)
        if self._process.is_alive():
            self._process.terminate()
            self._process.join(timeout=2)
        self._connection.close()
