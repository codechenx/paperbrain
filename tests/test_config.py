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
    assert loaded.summary_model == "gpt-4.1-mini"
    assert loaded.embedding_model == "text-embedding-3-small"


def test_config_stores_openai_and_gemini_fields(tmp_path: Path) -> None:
    config_path = tmp_path / "paperbrain.conf"
    store = ConfigStore(config_path)
    store.save(
        database_url="postgresql://localhost:5432/paperbrain",
        openai_api_key="sk-test",
        gemini_api_key="gm-test",
        summary_model="gpt-4.1-mini",
        embedding_model="text-embedding-3-small",
    )

    loaded = store.load()

    assert loaded.database_url == "postgresql://localhost:5432/paperbrain"
    assert loaded.openai_api_key == "sk-test"
    assert loaded.gemini_api_key == "gm-test"
    assert loaded.summary_model == "gpt-4.1-mini"
    assert loaded.embedding_model == "text-embedding-3-small"


def test_load_legacy_config_uses_model_defaults(tmp_path: Path) -> None:
    config_path = tmp_path / "paperbrain.conf"
    config_path.write_text(
        '[paperbrain]\ndatabase_url = "postgresql://localhost:5432/paperbrain"\n',
        encoding="utf-8",
    )
    loaded = ConfigStore(config_path).load()

    assert loaded.summary_model == "gpt-4.1-mini"
    assert loaded.embedding_model == "text-embedding-3-small"


def test_load_rejects_non_string_openai_api_key(tmp_path: Path) -> None:
    config_path = tmp_path / "paperbrain.conf"
    config_path.write_text(
        (
            "[paperbrain]\n"
            'database_url = "postgresql://localhost:5432/paperbrain"\n'
            "openai_api_key = 123\n"
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Invalid openai_api_key in configuration file"):
        ConfigStore(config_path).load()


def test_save_rejects_incompatible_embedding_model(tmp_path: Path) -> None:
    config_path = tmp_path / "paperbrain.conf"

    with pytest.raises(ValueError, match="text-embedding-3-small"):
        ConfigStore(config_path).save(
            database_url="postgresql://localhost:5432/paperbrain",
            embedding_model="text-embedding-3-large",
        )


def test_load_rejects_incompatible_embedding_model(tmp_path: Path) -> None:
    config_path = tmp_path / "paperbrain.conf"
    config_path.write_text(
        (
            "[paperbrain]\n"
            'database_url = "postgresql://localhost:5432/paperbrain"\n'
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
    ],
)
def test_load_rejects_non_string_model_values(
    tmp_path: Path, field: str, value: str, message: str
) -> None:
    config_path = tmp_path / "paperbrain.conf"
    config_path.write_text(
        (
            "[paperbrain]\n"
            'database_url = "postgresql://localhost:5432/paperbrain"\n'
            f"{field} = {value}\n"
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=message):
        ConfigStore(config_path).load()
