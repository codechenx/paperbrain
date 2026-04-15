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
        message = f"Schema apply failed: {exc}"
        lowered = str(exc).lower()
        if (
            "permission denied" in lowered
            and "extension" in lowered
            and ("vector" in lowered or "pg_trgm" in lowered)
        ):
                message = (
                    f"{message}. Ensure your database role has CREATE EXTENSION privileges, "
                    "or ask an admin for preinstalled extensions (vector/pg_trgm)."
                )
        raise RuntimeError(message) from exc
    return len(statements)
