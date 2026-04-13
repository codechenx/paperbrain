from pathlib import Path

from paperbrain.config import ConfigStore


def run_setup(database_url: str, config_path: Path) -> str:
    if not database_url.startswith("postgresql://"):
        raise ValueError("Database URL must start with postgresql://")
    store = ConfigStore(config_path)
    store.save(database_url=database_url)
    return f"Saved configuration to {config_path}"

