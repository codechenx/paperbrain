from paperbrain.db import connect, schema_statements


def build_init_sql(force: bool) -> list[str]:
    return schema_statements(force=force)


def run_init(database_url: str, force: bool) -> int:
    if not database_url.startswith("postgresql://"):
        raise ValueError("Database URL must start with postgresql://")
    statements = build_init_sql(force=force)
    try:
        with connect(database_url, autocommit=False) as connection:
            with connection.transaction():
                with connection.cursor() as cursor:
                    for statement in statements:
                        cursor.execute(statement)
    except Exception as exc:
        raise RuntimeError(f"Schema apply failed: {exc}") from exc
    return len(statements)
