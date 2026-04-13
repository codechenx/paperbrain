from dataclasses import dataclass
from pathlib import Path
import tomllib


@dataclass(slots=True)
class AppConfig:
    database_url: str


class ConfigStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def save(self, database_url: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        body = '[paperbrain]\ndatabase_url = "{value}"\n'.format(value=database_url.replace('"', '\\"'))
        self.path.write_text(body, encoding="utf-8")

    def load(self) -> AppConfig:
        if not self.path.exists():
            raise FileNotFoundError(f"Configuration file not found: {self.path}")
        parsed = tomllib.loads(self.path.read_text(encoding="utf-8"))
        section = parsed.get("paperbrain")
        if not isinstance(section, dict):
            raise ValueError("Missing [paperbrain] section in configuration file")
        database_url = section.get("database_url")
        if not isinstance(database_url, str) or not database_url.strip():
            raise ValueError("Missing non-empty database_url in configuration file")
        return AppConfig(database_url=database_url)

