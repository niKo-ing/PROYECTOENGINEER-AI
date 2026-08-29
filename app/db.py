from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

database_url = settings.sqlalchemy_database_url
if database_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
else:
    # psycopg v3 (libpq): bound connection attempts and detect a stale Supabase
    # pooler connection (silently dropped / half-open) so a failing roundtrip
    # can never block the API thread indefinitely.
    connect_args = {
        "connect_timeout": 10,
        "tcp_user_timeout": 30000,
        "keepalives": 1,
    }
engine = create_engine(database_url, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
