from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool

from galvanise.config import settings


class Base(DeclarativeBase):
    pass


kwargs = (
    {"connect_args": {"check_same_thread": False}}
    if settings.database_url.startswith("sqlite")
    else {}
)
if settings.database_url in ("sqlite://", "sqlite:///:memory:"):
    kwargs["poolclass"] = StaticPool
engine = create_engine(settings.database_url, **kwargs)
if settings.database_url.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def foreign_keys(conn, record):
        conn.execute("PRAGMA foreign_keys=ON")


SessionLocal = sessionmaker(engine, expire_on_commit=False)


def get_db():
    with SessionLocal() as db:
        yield db
