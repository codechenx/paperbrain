import hashlib
from typing import Protocol


class EmbeddingAdapter(Protocol):
    def embed(self, chunks: list[str]) -> list[list[float]]:
        ...


class DeterministicEmbeddingAdapter:
    def embed(self, chunks: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for chunk in chunks:
            digest = hashlib.sha256(chunk.encode("utf-8")).digest()
            vector: list[float] = []
            for i in range(8):
                value = int.from_bytes(digest[i * 4 : (i + 1) * 4], byteorder="big", signed=False)
                vector.append((value % 10_000) / 10_000.0)
            vectors.append(vector)
        return vectors

