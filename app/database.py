import os

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from .models import Base


def normalize_database_url(database_url):
    """Convert common Supabase URLs into SQLAlchemy-compatible driver URLs."""
    if database_url and database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+psycopg://", 1)

    if database_url and database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)

    return database_url


def get_database_url():
    return normalize_database_url(os.getenv("DATABASE_URL"))


def get_engine(database_url=None) -> Engine:
    resolved_url = normalize_database_url(database_url) if database_url else get_database_url()
    if not resolved_url:
        raise RuntimeError("DATABASE_URL is required to connect to Supabase")

    return create_engine(resolved_url, pool_pre_ping=True)


def get_session_factory(database_url=None):
    return sessionmaker(bind=get_engine(database_url), autoflush=False, expire_on_commit=False)


def init_db(database_url=None):
    """Create tables for local prototypes; use migrations for shared deployments."""
    engine = get_engine(database_url)
    Base.metadata.create_all(engine)
    return engine
