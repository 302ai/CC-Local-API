from __future__ import annotations

from peewee import Model


def bind_models(database, models: list[type[Model]]) -> None:
    for m in models:
        m._meta.database = database


def detect_missing_columns(database, models: list[type[Model]]) -> list[tuple[str, str]]:
    """Return a list of (table_name, column_name) that are missing in DB."""
    missing: list[tuple[str, str]] = []

    for m in models:
        table = m._meta.table_name
        existing_cols: set[str] = set()
        for col in database.execute_sql(f"PRAGMA table_info({table})").fetchall():
            existing_cols.add(col[1])

        for f in m._meta.sorted_fields:
            col_name = f.column_name
            if col_name not in existing_cols:
                missing.append((table, col_name))

    return missing


def auto_migrate_add_missing_columns(database, models: list[type[Model]]) -> bool:
    """Best-effort SQLite auto-migration: add missing columns only.

    Returns True if any schema change was applied.

    - Only issues: CREATE TABLE (if missing) + ALTER TABLE .. ADD COLUMN (if missing)
    - Does NOT drop/modify columns, types, constraints, or foreign keys.
    """
    # Ensure tables exist first.
    database.create_tables(models)

    changed = False

    for m in models:
        table = m._meta.table_name

        existing_cols: set[str] = set()
        for col in database.execute_sql(f"PRAGMA table_info({table})").fetchall():
            # PRAGMA table_info returns: cid, name, type, notnull, dflt_value, pk
            existing_cols.add(col[1])

        for f in m._meta.sorted_fields:
            col_name = f.column_name
            if col_name in existing_cols:
                continue

            # Compile peewee field DDL to SQL (quote column names correctly).
            ctx = database.get_sql_context()
            node = f.ddl(ctx)
            col_sql, params = ctx.sql(node).query()
            if params:
                # SQLite ALTER TABLE ADD COLUMN does not support bound params for DDL.
                raise ValueError(f"DDL params not supported for {table}.{col_name}: {params!r}")

            database.execute_sql(f"ALTER TABLE {table} ADD COLUMN {col_sql}")
            changed = True

            # Backfill existing rows ONLY when the field is NOT NULL and has a non-callable default.
            # This keeps semantics for nullable fields (NULL remains meaningful).
            if not f.null:
                default_val = getattr(f, "default", None)
                if default_val is not None and not callable(default_val):
                    # Use bound params for UPDATE (safe), unlike DDL which can't be parametrized in SQLite.
                    database.execute_sql(
                        f"UPDATE {table} SET {col_name} = ? WHERE {col_name} IS NULL",
                        (default_val,),
                    )

    return changed


class BaseModel(Model):
    class Meta:
        database = None  # 运行时绑定
