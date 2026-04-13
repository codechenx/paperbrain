from paperbrain.db import schema_statements


def build_init_sql(force: bool) -> list[str]:
    return schema_statements(force=force)

