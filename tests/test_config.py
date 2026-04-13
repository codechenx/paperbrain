from pathlib import Path

from paperbrain.config import ConfigStore


def test_save_and_load_config_round_trip(tmp_path: Path) -> None:
    config_path = tmp_path / "paperbrain.conf"
    store = ConfigStore(config_path)
    store.save(database_url="postgresql://localhost:5432/paperbrain")
    loaded = store.load()
    assert loaded.database_url == "postgresql://localhost:5432/paperbrain"


def test_config_stores_openai_fields(tmp_path: Path) -> None:
    config_path = tmp_path / "paperbrain.conf"
    store = ConfigStore(config_path)
    store.save(
        database_url="postgresql://localhost:5432/paperbrain",
        openai_api_key="sk-test",
        summary_model="gpt-4.1-mini",
        embedding_model="text-embedding-3-small",
    )

    loaded = store.load()

    assert loaded.database_url == "postgresql://localhost:5432/paperbrain"
    assert loaded.openai_api_key == "sk-test"
    assert loaded.summary_model == "gpt-4.1-mini"
    assert loaded.embedding_model == "text-embedding-3-small"
