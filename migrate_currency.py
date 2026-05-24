import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "passengers.db"

CANDIDATE_TABLES = [
    "trip_passengers",
    "trip_passenger",
    "passengers",
    "trip_passengers",  # дублирано не пречи
]

def table_columns(cur, table: str):
    cur.execute(f"PRAGMA table_info({table})")
    return [row[1] for row in cur.fetchall()]  # row[1] = column name

def main():
    if not DB_PATH.exists():
        raise SystemExit(f"DB file not found: {DB_PATH}")

    con = sqlite3.connect(str(DB_PATH))
    cur = con.cursor()

    # Ако не знаем таблицата - пробваме кандидатите
    for t in CANDIDATE_TABLES:
        try:
            cols = table_columns(cur, t)
        except Exception:
            continue

        if "currency" in cols:
            print(f"OK: column already exists in {t}")
            con.close()
            return

        try:
            cur.execute(f"ALTER TABLE {t} ADD COLUMN currency TEXT DEFAULT 'EUR'")
            con.commit()
            print(f"OK: added currency column to {t}")
            con.close()
            return
        except Exception as e:
            print(f"SKIP: {t} -> {e}")

    # Ако не сме намерили таблица, покажи всички таблици
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cur.fetchall()]
    con.close()
    raise SystemExit(
        "Could not add column. Existing tables: " + ", ".join(tables)
    )

if __name__ == "__main__":
    main()
