from __future__ import annotations

from dataclasses import asdict
from multiprocessing import get_context
from multiprocessing.connection import Connection
from pathlib import Path

from paperbrain.adapters.docling import DoclingParser
from paperbrain.models import ParsedPaper


def _worker_main(connection: Connection, ocr_enabled: bool) -> None:
    parser = DoclingParser(ocr_enabled=ocr_enabled)
    converter = parser.create_converter()
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
                parsed = parser.parse_pdf_with_converter(Path(str(payload)), converter)
            except Exception as exc:
                connection.send(("error", f"{type(exc).__name__}: {exc}"))
                continue
            connection.send(("ok", asdict(parsed)))
    finally:
        connection.close()


class DoclingParseWorker:
    def __init__(self, *, ocr_enabled: bool = False) -> None:
        context = get_context("spawn")
        parent_connection, child_connection = context.Pipe()
        self._connection = parent_connection
        self._process = context.Process(target=_worker_main, args=(child_connection, ocr_enabled))
        self._process.start()
        child_connection.close()

    def parse(self, path: Path) -> ParsedPaper:
        if not self._process.is_alive():
            raise RuntimeError("Docling worker process is not running")
        self._connection.send(("parse", str(path)))
        status, payload = self._connection.recv()
        if status != "ok":
            raise RuntimeError(str(payload))
        if not isinstance(payload, dict):
            raise RuntimeError("Docling worker returned an invalid payload")
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
