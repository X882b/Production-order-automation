import os
from sqlalchemy import create_engine


def _build_dsn() -> str:
    dsn = os.getenv("PG_DSN")
    if dsn:
        return dsn
    user = os.environ["PG_USER"]
    password = os.environ["PG_PASS"]
    db = os.environ["PG_DB"]
    host = os.getenv("PG_HOST", "db")
    port = os.getenv("PG_PORT", "5432")
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"


engine = create_engine(_build_dsn(), future=True, pool_pre_ping=True)
