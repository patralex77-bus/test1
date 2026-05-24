import argparse
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import create_engine, MetaData, Table, text, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError


DEFAULT_TABLES = ["trips", "trip_passengers"]


def parse_dt(v: Any) -> Any:
    """Опит да превърне ISO string към datetime; ако не стане, връща както е."""
    if v is None:
        return None
    if isinstance(v, datetime):
        return v
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return v
        # sqlite понякога пази '2024-04-02 00:00:00'
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            return v
    return v


def reflect_table(engine: Engine, name: str) -> Optional[Table]:
    md = MetaData()
    try:
        return Table(name, md, autoload_with=engine)
    except SQLAlchemyError:
        return None


def common_columns(src: Table, dst: Table) -> List[str]:
    src_cols = {c.name for c in src.columns}
    dst_cols = {c.name for c in dst.columns}
    # запази реда от dst
    return [c.name for c in dst.columns if c.name in src_cols]


def fetch_rows(engine: Engine, table: Table) -> List[Dict[str, Any]]:
    with engine.connect() as conn:
        rows = conn.execute(select(table)).mappings().all()
        return [dict(r) for r in rows]


def chunked(seq: List[Dict[str, Any]], size: int = 500) -> List[List[Dict[str, Any]]]:
    return [seq[i : i + size] for i in range(0, len(seq), size)]


def set_pg_sequence(engine: Engine, table_name: str, id_col: str = "id"):
    # Set sequence to max(id) so future inserts without id work
    with engine.begin() as conn:
        max_id = conn.execute(text(f"SELECT MAX({id_col}) FROM {table_name}")).scalar()
        if max_id is None:
            return
        conn.execute(
            text(
                """
                SELECT setval(
                  pg_get_serial_sequence(:tbl, :col),
                  :val,
                  true
                )
                """
            ),
            {"tbl": table_name, "col": id_col, "val": int(max_id)},
        )


def truncate_tables(engine: Engine, table_names: List[str]):
    # For Postgres: TRUNCATE ... RESTART IDENTITY CASCADE
    with engine.begin() as conn:
        for t in table_names:
            conn.execute(text(f"TRUNCATE TABLE {t} RESTART IDENTITY CASCADE"))


def migrate_table(
    src_engine: Engine,
    dst_engine: Engine,
    table_name: str,
    dry_run: bool = False,
):
    src = reflect_table(src_engine, table_name)
    dst = reflect_table(dst_engine, table_name)

    # IMPORTANT: SQLAlchemy Table/Clause не може да се ползва в boolean context
    if src is None:
        print(f"[MIGRATE] Skip '{table_name}': няма такава таблица в SQLite")
        return
    if dst is None:
        print(f"[MIGRATE] Skip '{table_name}': няма такава таблица в Postgres")
        return

    cols = common_columns(src, dst)
    if not cols:
        print(f"[MIGRATE] Skip '{table_name}': няма общи колони")
        return

    rows = fetch_rows(src_engine, src)
    if not rows:
        print(f"[MIGRATE] '{table_name}': 0 реда")
        return

    # вземи само общите колони
    cleaned: List[Dict[str, Any]] = []
    for r in rows:
        item = {k: r.get(k) for k in cols}
        # лек постпроцес за datetime полета
        for k, v in list(item.items()):
            item[k] = parse_dt(v)
        cleaned.append(item)

    print(f"[MIGRATE] '{table_name}': {len(cleaned)} реда, колони: {cols}")

    if dry_run:
        print("[MIGRATE] dry-run: няма запис в Postgres")
        return

    with dst_engine.begin() as conn:
        for part in chunked(cleaned, 500):
            conn.execute(dst.insert(), part)

    # ако има id — оправяме sequence
    if "id" in cols:
        try:
            set_pg_sequence(dst_engine, table_name, "id")
        except Exception as e:
            print(f"[MIGRATE] WARN: не успях да setval за '{table_name}': {e}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sqlite", required=True, help="пример: sqlite:///passengers.db")
    ap.add_argument("--postgres", required=True, help="Postgres DATABASE_URL")
    ap.add_argument("--tables", default=",".join(DEFAULT_TABLES), help="comma-separated")
    ap.add_argument("--truncate", action="store_true", help="TRUNCATE целевите таблици преди миграция")
    ap.add_argument("--dry-run", action="store_true", help="само печат, без запис")
    args = ap.parse_args()

    tables = [t.strip() for t in args.tables.split(",") if t.strip()]

    src_engine = create_engine(args.sqlite, future=True)
    dst_engine = create_engine(args.postgres, future=True)

    # важен ред при FK: първо trips, после trip_passengers
    ordered = []
    for t in DEFAULT_TABLES:
        if t in tables:
            ordered.append(t)
    for t in tables:
        if t not in ordered:
            ordered.append(t)

    if args.truncate and not args.dry_run:
        print("[MIGRATE] Truncate Postgres tables:", ordered)
        truncate_tables(dst_engine, ordered)

    for t in ordered:
        migrate_table(src_engine, dst_engine, t, dry_run=args.dry_run)

    print("[MIGRATE] Done.")


if __name__ == "__main__":
    main()
