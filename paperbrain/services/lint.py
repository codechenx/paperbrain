from dataclasses import dataclass

from paperbrain.db import connect
from paperbrain.quality import ensure_frontmatter_fields, normalize_whitespace, remove_dead_links


@dataclass(slots=True)
class LintStats:
    checked: int
    fixed: int


def lint_markdown(text: str, known_slugs: set[str]) -> str:
    cleaned = normalize_whitespace(text)
    linked = remove_dead_links(cleaned, known_slugs)
    return ensure_frontmatter_fields(linked, {"slug": "unknown", "type": "unknown"})


class DatabaseLintRepository:
    TABLES = ("paper_cards", "person_cards", "topic_cards")

    def __init__(self, connection: object) -> None:
        self.connection = connection

    def list_documents(self) -> list[tuple[str, str, str]]:
        rows: list[tuple[str, str, str]] = []
        with self.connection.cursor() as cursor:
            for table in self.TABLES:
                cursor.execute(f"SELECT slug, body FROM {table} ORDER BY slug;")
                rows.extend((table, str(slug), str(body)) for slug, body in cursor.fetchall())
        return rows

    def update_document(self, table: str, slug: str, content: str) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(f"UPDATE {table} SET body = %s WHERE slug = %s;", (content, slug))


def run_lint(database_url: str) -> LintStats:
    if not database_url.startswith("postgresql://"):
        raise ValueError("Database URL must start with postgresql://")

    with connect(database_url, autocommit=False) as connection:
        repo = DatabaseLintRepository(connection)
        rows = repo.list_documents()
        known_slugs = {slug for _, slug, _ in rows}

        fixed = 0
        with connection.transaction():
            for table, slug, body in rows:
                linted = lint_markdown(body, known_slugs)
                if linted != body:
                    repo.update_document(table, slug, linted)
                    fixed += 1

    return LintStats(checked=len(rows), fixed=fixed)
