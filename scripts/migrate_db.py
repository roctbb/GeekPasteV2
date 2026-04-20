#!/usr/bin/env python3
import argparse
import os
from typing import Dict, Any, List

from sqlalchemy import Boolean, Integer, MetaData, create_engine, select, text


def parse_args():
    parser = argparse.ArgumentParser(
        description="Copy application data from current DB to target DB (for Docker/Postgres migration)."
    )
    parser.add_argument(
        "--source",
        default=os.getenv("SOURCE_DB_URL", "sqlite:///database.sqlite"),
        help="Source SQLAlchemy URL (default: sqlite:///database.sqlite or SOURCE_DB_URL).",
    )
    parser.add_argument(
        "--target",
        default=os.getenv("TARGET_DB_URL") or os.getenv("CONNECTION_STRING"),
        help="Target SQLAlchemy URL (default: TARGET_DB_URL or CONNECTION_STRING).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1000,
        help="Rows per insert batch.",
    )
    parser.add_argument(
        "--no-truncate",
        action="store_true",
        help="Do not clear target tables before copy (append mode).",
    )
    return parser.parse_args()


def order_tables(table_names: List[str]) -> List[str]:
    preferred = ["tasks", "codes", "similarities", "alembic_version"]
    ordered = [name for name in preferred if name in table_names]
    for name in table_names:
        if name not in ordered:
            ordered.append(name)
    return ordered


def normalize_row(row: Dict[str, Any], dst_table) -> Dict[str, Any]:
    normalized = {}
    for col in dst_table.columns:
        if col.name not in row:
            continue
        value = row[col.name]
        if isinstance(col.type, Boolean) and isinstance(value, int):
            value = bool(value)
        normalized[col.name] = value
    return normalized


def truncate_target_tables(dst_conn, dst_dialect: str, table_names: List[str]):
    for table_name in reversed(table_names):
        if dst_dialect == "postgresql":
            dst_conn.execute(text(f'TRUNCATE TABLE "{table_name}" RESTART IDENTITY CASCADE'))
        else:
            dst_conn.execute(text(f'DELETE FROM "{table_name}"'))


def reset_sequences(dst_conn, dst_dialect: str, table_names: List[str], dst_meta: MetaData):
    if dst_dialect != "postgresql":
        return

    for table_name in table_names:
        table = dst_meta.tables[table_name]
        for col in table.columns:
            if col.primary_key and isinstance(col.type, Integer):
                try:
                    dst_conn.execute(
                        text(
                            f"SELECT setval("
                            f"pg_get_serial_sequence('\"{table_name}\"', '{col.name}'), "
                            f"COALESCE(MAX(\"{col.name}\"), 1), "
                            f"MAX(\"{col.name}\") IS NOT NULL"
                            f") FROM \"{table_name}\""
                        )
                    )
                except Exception:
                    # Ignore non-serial PKs.
                    pass


def main():
    args = parse_args()

    if not args.target:
        raise SystemExit("Target DB URL is required (use --target or TARGET_DB_URL/CONNECTION_STRING).")

    src_engine = create_engine(args.source)
    dst_engine = create_engine(args.target)

    src_meta = MetaData()
    dst_meta = MetaData()
    src_meta.reflect(bind=src_engine)
    dst_meta.reflect(bind=dst_engine)

    common_tables = [name for name in src_meta.tables.keys() if name in dst_meta.tables.keys()]
    if not common_tables:
        raise SystemExit("No common tables found between source and target.")

    ordered_tables = order_tables(common_tables)

    print(f"Source: {args.source}")
    print(f"Target: {args.target}")
    print(f"Tables: {ordered_tables}")

    with src_engine.connect() as src_conn, dst_engine.begin() as dst_conn:
        if not args.no_truncate:
            truncate_target_tables(dst_conn, dst_engine.dialect.name, ordered_tables)

        for table_name in ordered_tables:
            src_table = src_meta.tables[table_name]
            dst_table = dst_meta.tables[table_name]
            result = src_conn.execute(select(src_table))

            copied = 0
            batch = []
            for row in result.mappings():
                batch.append(normalize_row(row, dst_table))
                if len(batch) >= args.batch_size:
                    dst_conn.execute(dst_table.insert(), batch)
                    copied += len(batch)
                    batch.clear()

            if batch:
                dst_conn.execute(dst_table.insert(), batch)
                copied += len(batch)

            print(f"Copied {copied} rows -> {table_name}")

        reset_sequences(dst_conn, dst_engine.dialect.name, ordered_tables, dst_meta)

    print("Migration completed.")


if __name__ == "__main__":
    main()
