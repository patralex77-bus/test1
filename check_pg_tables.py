from app.db import engine
from sqlalchemy import text

with engine.connect() as c:
    rows = c.execute(text(
        "SELECT table_name "
        "FROM information_schema.tables "
        "WHERE table_schema='public' "
        "ORDER BY table_name"
    )).all()
    print([r[0] for r in rows])
