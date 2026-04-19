from pathlib import Path
import os
import stat

import pytest

from paperbrain.config import ConfigStore


def test_save_and_load_config_round_trip(tmp_path: Path) -> None:
    config_path = tmp_path / "paperbrain.conf"
    store = ConfigStore(config_path)
    store.save(database_url="postgresql://localhost:5432/paperbrain")
    loaded = store.load()
    assert loaded.database_url == "postgresql://localhost:5432/paperbrain"
    assert loaded.summary_model == "openai:gpt-4.1-mini"
    assert loaded.embedding_model == "text-embedding-3-small"
    assert loaded.embeddings_enabled is False
    assert loaded.ocr_enabled is False
    assert loaded.pdf_parser == "marker"


def test_config_stores_openai_and_gemini_fields(tmp_path: Path) -> None:
    config_path = tmp_path / "paperbrain.conf"
    store = ConfigStore(config_path)
    store.save(
        database_url="postgresql://localhost:5432/paperbrain",
        openai_api_key="sk-test",
        gemini_api_key="gm-test",
        summary_model="openai:gpt-4.1-mini",
        embedding_model="text-embedding-3-small",
    )

    loaded = store.load()

    assert loaded.database_url == "postgresql://localhost:5432/paperbrain"
    assert loaded.openai_api_key == "sk-test"
    assert loaded.gemini_api_key == "gm-test"
    assert loaded.summary_model == "openai:gpt-4.1-mini"
    assert loaded.embedding_model == "text-embedding-3-small"
    assert loaded.embeddings_enabled is False
    assert loaded.ocr_enabled is False
    assert loaded.pdf_parser == "marker"


def test_config_stores_ollama_fields(tmp_path: Path) -> None:
    config_path = tmp_path / "paperbrain.conf"
    store = ConfigStore(config_path)
    store.save(
        database_url="postgresql://localhost:5432/paperbrain",
        ollama_api_key="ol-test",
        ollama_base_url="https://ollama.local",
    )

    loaded = store.load()

    assert loaded.ollama_api_key == "ol-test"
    assert loaded.ollama_base_url == "https://ollama.local"


def test_save_normalizes_ollama_base_url(tmp_path: Path) -> None:
    config_path = tmp_path / "paperbrain.conf"
    store = ConfigStore(config_path)
    store.save(
        database_url="postgresql://localhost:5432/paperbrain",
        ollama_base_url="  https://ollama.local/base  ",
    )

    loaded = store.load()

    assert loaded.ollama_base_url == "https://ollama.local/base"


def test_save_rejects_blank_ollama_base_url(tmp_path: Path) -> None:
    config_path = tmp_path / "paperbrain.conf"
    store = ConfigStore(config_path)

    with pytest.raises(ValueError, match="non-empty ollama_base_url"):
        store.save(
            database_url="postgresql://localhost:5432/paperbrain",
            ollama_base_url="   \n\t ",
        )


def test_load_rejects_blank_ollama_base_url(tmp_path: Path) -> None:
    config_path = tmp_path / "paperbrain.conf"
    config_path.write_text(
        (
            "[paperbrain]\n"
            'database_url = "postgresql://localhost:5432/paperbrain"\n'
            "embeddings_enabled = false\n"
            "ocr_enabled = false\n"
            'pdf_parser = "marker"\n'
            'ollama_base_url = "   "\n'
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="non-empty ollama_base_url"):
        ConfigStore(config_path).load()


def test_load_config_uses_model_defaults_for_optional_fields(tmp_path: Path) -> None:
    config_path = tmp_path / "paperbrain.conf"
    config_path.write_text(
        (
            "[paperbrain]\n"
            'database_url = "postgresql://localhost:5432/paperbrain"\n'
            "embeddings_enabled = false\n"
            "ocr_enabled = false\n"
            'pdf_parser = "marker"\n'
        ),
        encoding="utf-8",
    )
    loaded = ConfigStore(config_path).load()

    assert loaded.gemini_api_key == ""
    assert loaded.ollama_api_key == ""
    assert loaded.ollama_base_url == "https://ollama.com"
    assert loaded.summary_model == "openai:gpt-4.1-mini"
    assert loaded.embedding_model == "text-embedding-3-small"
    assert loaded.embeddings_enabled is False
    assert loaded.ocr_enabled is False
    assert loaded.pdf_parser == "marker"


def test_load_rejects_missing_embeddings_enabled_key(tmp_path: Path) -> None:
    config_path = tmp_path / "paperbrain.conf"
    config_path.write_text(
        (
            "[paperbrain]\n"
            'database_url = "postgresql://localhost:5432/paperbrain"\n'
            "ocr_enabled = false\n"
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="embeddings_enabled"):
        ConfigStore(config_path).load()


def test_load_rejects_missing_ocr_enabled_key(tmp_path: Path) -> None:
    config_path = tmp_path / "paperbrain.conf"
    config_path.write_text(
        (
            "[paperbrain]\n"
            'database_url = "postgresql://localhost:5432/paperbrain"\n'
            "embeddings_enabled = false\n"
            'pdf_parser = "marker"\n'
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="ocr_enabled"):
        ConfigStore(config_path).load()


def test_load_rejects_legacy_docling_ocr_enabled_without_ocr_enabled(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "paperbrain.conf"
    config_path.write_text(
        (
            "[paperbrain]\n"
            'database_url = "postgresql://localhost:5432/paperbrain"\n'
            "embeddings_enabled = false\n"
            "docling_ocr_enabled = true\n"
            'pdf_parser = "docling"\n'
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="ocr_enabled"):
        ConfigStore(config_path).load()


def test_load_rejects_missing_pdf_parser_key(tmp_path: Path) -> None:
    config_path = tmp_path / "paperbrain.conf"
    config_path.write_text(
        (
            "[paperbrain]\n"
            'database_url = "postgresql://localhost:5432/paperbrain"\n'
            "embeddings_enabled = false\n"
            "ocr_enabled = false\n"
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="pdf_parser"):
        ConfigStore(config_path).load()


def test_load_rejects_invalid_pdf_parser_value(tmp_path: Path) -> None:
    config_path = tmp_path / "paperbrain.conf"
    config_path.write_text(
        (
            "[paperbrain]\n"
            'database_url = "postgresql://localhost:5432/paperbrain"\n'
            "embeddings_enabled = false\n"
            "ocr_enabled = false\n"
            'pdf_parser = "invalid"\n'
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="pdf_parser"):
        ConfigStore(config_path).load()


def test_load_rejects_non_string_openai_api_key(tmp_path: Path) -> None:
    config_path = tmp_path / "paperbrain.conf"
    config_path.write_text(
        (
            "[paperbrain]\n"
            'database_url = "postgresql://localhost:5432/paperbrain"\n'
            "embeddings_enabled = false\n"
            "ocr_enabled = false\n"
            'pdf_parser = "marker"\n'
            "openai_api_key = 123\n"
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Invalid openai_api_key in configuration file"):
        ConfigStore(config_path).load()


def test_save_allows_incompatible_embedding_model_when_embeddings_disabled(tmp_path: Path) -> None:
    config_path = tmp_path / "paperbrain.conf"

    ConfigStore(config_path).save(
        database_url="postgresql://localhost:5432/paperbrain",
        embedding_model="text-embedding-3-large",
        embeddings_enabled=False,
    )

    loaded = ConfigStore(config_path).load()
    assert loaded.embedding_model == "text-embedding-3-large"
    assert loaded.embeddings_enabled is False


def test_save_rejects_incompatible_embedding_model_when_embeddings_enabled(tmp_path: Path) -> None:
    config_path = tmp_path / "paperbrain.conf"

    with pytest.raises(ValueError, match="text-embedding-3-small"):
        ConfigStore(config_path).save(
            database_url="postgresql://localhost:5432/paperbrain",
            embedding_model="text-embedding-3-large",
            embeddings_enabled=True,
        )


def test_load_rejects_incompatible_embedding_model_when_embeddings_enabled(tmp_path: Path) -> None:
    config_path = tmp_path / "paperbrain.conf"
    config_path.write_text(
        (
            "[paperbrain]\n"
            'database_url = "postgresql://localhost:5432/paperbrain"\n'
            "embeddings_enabled = true\n"
            "ocr_enabled = false\n"
            'pdf_parser = "marker"\n'
            'embedding_model = "text-embedding-3-large"\n'
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="text-embedding-3-small"):
        ConfigStore(config_path).load()


@pytest.mark.skipif(os.name != "posix", reason="POSIX-only permission mode semantics")
def test_save_sets_restrictive_permissions(tmp_path: Path) -> None:
    config_path = tmp_path / "paperbrain.conf"
    store = ConfigStore(config_path)

    store.save(database_url="postgresql://localhost:5432/paperbrain")

    mode = stat.S_IMODE(config_path.stat().st_mode)
    assert mode == 0o600


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("summary_model", "123", "Invalid summary_model in configuration file"),
        ("embedding_model", "456", "Invalid embedding_model in configuration file"),
        ("embeddings_enabled", '"yes"', "Invalid embeddings_enabled in configuration file"),
        ("ocr_enabled", '"yes"', "Invalid ocr_enabled in configuration file"),
        ("pdf_parser", "123", "Invalid pdf_parser in configuration file"),
        ("ollama_api_key", "789", "Invalid ollama_api_key in configuration file"),
        ("ollama_base_url", "789", "Invalid ollama_base_url in configuration file"),
    ],
)
def test_load_rejects_non_string_model_values(
    tmp_path: Path, field: str, value: str, message: str
) -> None:
    config_path = tmp_path / "paperbrain.conf"
    required_flags = []
    if field != "embeddings_enabled":
        required_flags.append("embeddings_enabled = false\n")
    if field != "ocr_enabled":
        required_flags.append("ocr_enabled = false\n")
    if field != "pdf_parser":
        required_flags.append('pdf_parser = "marker"\n')
    config_path.write_text(
        (
            "[paperbrain]\n"
            'database_url = "postgresql://localhost:5432/paperbrain"\n'
            f"{''.join(required_flags)}"
            f"{field} = {value}\n"
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=message):
        ConfigStore(config_path).load()
