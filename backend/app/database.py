from sqlalchemy.orm.session import Session


import os
from threading import RLock

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from .models import Base


_ENGINE_LOCK = RLock()
_CACHED_ENGINE: Engine | None = None
_CACHED_SESSION_FACTORY = None
_CACHED_DATABASE_URL: str | None = None


def _run_startup_migrations(engine: Engine):
    """Apply lightweight, idempotent compatibility migrations."""
    with engine.begin() as connection:
        has_is_correct = bool(
            connection.execute(
                text(
                    """
                    SELECT EXISTS (
                      SELECT 1
                      FROM information_schema.columns
                      WHERE table_name = 'participant_responses'
                        AND column_name = 'is_correct'
                    )
                    """
                )
            ).scalar()
        )
        has_is_flagged = bool(
            connection.execute(
                text(
                    """
                    SELECT EXISTS (
                      SELECT 1
                      FROM information_schema.columns
                      WHERE table_name = 'participant_responses'
                        AND column_name = 'is_flagged'
                    )
                    """
                )
            ).scalar()
        )

        if not has_is_correct:
            connection.execute(
                text(
                    "ALTER TABLE participant_responses ADD COLUMN IF NOT EXISTS is_correct text"
                )
            )

        if has_is_flagged:
            connection.execute(
                text(
                    """
                    UPDATE participant_responses
                    SET is_correct = CASE
                        WHEN is_correct IS NOT NULL THEN is_correct
                        WHEN is_flagged THEN 'pending'
                        ELSE 'yes (auto)'
                    END
                    """
                )
            )
        else:
            connection.execute(
                text(
                    """
                    UPDATE participant_responses
                    SET is_correct = COALESCE(is_correct, 'pending')
                    """
                )
            )

        connection.execute(
            text(
                """
                ALTER TABLE participant_responses
                ALTER COLUMN is_correct SET DEFAULT 'pending'
                """
            )
        )
        connection.execute(
            text(
                """
                UPDATE participant_responses
                SET review_status = 'auto'
                WHERE review_status = 'not_flagged'
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS idx_participant_responses_is_correct
                ON participant_responses(is_correct)
                """
            )
        )

        has_qa_items_language = bool(
            connection.execute(
                text(
                    """
                    SELECT EXISTS (
                      SELECT 1
                      FROM information_schema.columns
                      WHERE table_name = 'qa_items'
                        AND column_name = 'language'
                    )
                    """
                )
            ).scalar()
        )
        if has_qa_items_language:
            connection.execute(text("DROP INDEX IF EXISTS idx_qa_items_language"))
            connection.execute(text("ALTER TABLE qa_items DROP COLUMN language"))

        connection.execute(
            text("ALTER TABLE qa_items ADD COLUMN IF NOT EXISTS passage_text text")
        )
        connection.execute(
            text(
                "ALTER TABLE qa_items ADD COLUMN IF NOT EXISTS original_question_text text"
            )
        )
        connection.execute(
            text(
                "ALTER TABLE qa_items ADD COLUMN IF NOT EXISTS original_expected_answer text"
            )
        )
        connection.execute(
            text(
                "ALTER TABLE qa_items ADD COLUMN IF NOT EXISTS review_removed_at timestamptz"
            )
        )
        connection.execute(
            text(
                """
                UPDATE qa_items
                SET original_question_text = question_text
                WHERE original_question_text IS NULL
                """
            )
        )
        connection.execute(
            text(
                """
                UPDATE qa_items
                SET original_expected_answer = expected_answer
                WHERE original_expected_answer IS NULL
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS idx_qa_items_review_removed_at
                ON qa_items(review_removed_at)
                """
            )
        )
        connection.execute(
            text(
                "ALTER TABLE qa_items ADD COLUMN IF NOT EXISTS qa_reviewed_at timestamptz"
            )
        )
        connection.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS idx_qa_items_qa_reviewed_at
                ON qa_items(qa_reviewed_at)
                """
            )
        )
        connection.execute(
            text(
                "ALTER TABLE qa_items ADD COLUMN IF NOT EXISTS question_type text NOT NULL DEFAULT 'open'"
            )
        )
        connection.execute(
            text(
                "ALTER TABLE qa_items ADD COLUMN IF NOT EXISTS mcq_choices jsonb NOT NULL DEFAULT '[]'::jsonb"
            )
        )
        connection.execute(
            text(
                "ALTER TABLE qa_items ADD COLUMN IF NOT EXISTS mcq_correct_choice text"
            )
        )
        connection.execute(
            text(
                "ALTER TABLE qa_items ADD COLUMN IF NOT EXISTS original_question_type text"
            )
        )
        connection.execute(
            text(
                "ALTER TABLE qa_items ADD COLUMN IF NOT EXISTS original_mcq_choices jsonb NOT NULL DEFAULT '[]'::jsonb"
            )
        )
        connection.execute(
            text(
                "ALTER TABLE qa_items ADD COLUMN IF NOT EXISTS original_mcq_correct_choice text"
            )
        )
        has_mcq_correct_index = bool(
            connection.execute(
                text(
                    """
                    SELECT EXISTS (
                      SELECT 1
                      FROM information_schema.columns
                      WHERE table_name = 'qa_items'
                        AND column_name = 'mcq_correct_index'
                    )
                    """
                )
            ).scalar()
        )
        if has_mcq_correct_index:
            connection.execute(
                text(
                    """
                    UPDATE qa_items
                    SET mcq_correct_choice = chr(65 + mcq_correct_index)
                    WHERE mcq_correct_choice IS NULL
                      AND mcq_correct_index IS NOT NULL
                      AND mcq_correct_index BETWEEN 0 AND 3
                    """
                )
            )
            connection.execute(
                text(
                    """
                    UPDATE qa_items
                    SET original_mcq_correct_choice = chr(65 + original_mcq_correct_index)
                    WHERE original_mcq_correct_choice IS NULL
                      AND original_mcq_correct_index IS NOT NULL
                      AND original_mcq_correct_index BETWEEN 0 AND 3
                    """
                )
            )
            connection.execute(
                text("ALTER TABLE qa_items DROP COLUMN IF EXISTS mcq_correct_index")
            )
            connection.execute(
                text(
                    "ALTER TABLE qa_items DROP COLUMN IF EXISTS original_mcq_correct_index"
                )
            )

        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS qa_item_language_keywords (
                    qa_item_id text NOT NULL REFERENCES qa_items(id) ON DELETE CASCADE,
                    language text NOT NULL,
                    required_keywords jsonb NOT NULL DEFAULT '[]'::jsonb,
                    optional_keywords jsonb NOT NULL DEFAULT '[]'::jsonb,
                    required_keyword_specs jsonb NOT NULL DEFAULT '[]'::jsonb,
                    optional_keyword_specs jsonb NOT NULL DEFAULT '[]'::jsonb,
                    updated_by text,
                    created_at timestamptz NOT NULL DEFAULT now(),
                    updated_at timestamptz NOT NULL DEFAULT now(),
                    PRIMARY KEY (qa_item_id, language)
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS idx_qa_item_language_keywords_language
                ON qa_item_language_keywords(language)
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS qa_item_keyword_recordings (
                    id text PRIMARY KEY DEFAULT gen_random_uuid()::text,
                    qa_item_id text NOT NULL REFERENCES qa_items(id) ON DELETE CASCADE,
                    language text NOT NULL,
                    keyword_kind text NOT NULL,
                    keyword_text text NOT NULL,
                    version int NOT NULL DEFAULT 1,
                    storage_uri text NOT NULL,
                    content_type text,
                    uploaded_by text,
                    created_at timestamptz NOT NULL DEFAULT now(),
                    CONSTRAINT ck_qa_item_keyword_recordings_kind
                        CHECK (keyword_kind IN ('required', 'optional')),
                    CONSTRAINT uq_qa_item_keyword_recordings_version
                        UNIQUE (qa_item_id, language, keyword_kind, keyword_text, version)
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS idx_qa_item_keyword_recordings_qa_item
                ON qa_item_keyword_recordings(qa_item_id)
                """
            )
        )


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

    global _CACHED_ENGINE, _CACHED_DATABASE_URL
    if _CACHED_ENGINE is not None and _CACHED_DATABASE_URL == resolved_url:
        return _CACHED_ENGINE

    with _ENGINE_LOCK:
        if _CACHED_ENGINE is not None and _CACHED_DATABASE_URL == resolved_url:
            return _CACHED_ENGINE

        engine = create_engine(resolved_url, pool_pre_ping=True)
        _run_startup_migrations(engine)
        _CACHED_ENGINE = engine
        _CACHED_DATABASE_URL = resolved_url
        return _CACHED_ENGINE


def get_session_factory(database_url=None):
    resolved_url = normalize_database_url(database_url) if database_url else get_database_url()
    if not resolved_url:
        raise RuntimeError("DATABASE_URL is required to connect to Supabase")

    global _CACHED_SESSION_FACTORY
    if _CACHED_SESSION_FACTORY is not None and _CACHED_DATABASE_URL == resolved_url:
        return _CACHED_SESSION_FACTORY

    with _ENGINE_LOCK:
        if _CACHED_SESSION_FACTORY is not None and _CACHED_DATABASE_URL == resolved_url:
            return _CACHED_SESSION_FACTORY
        engine = get_engine(resolved_url)
        _CACHED_SESSION_FACTORY = sessionmaker[Session](
            bind=engine,
            autoflush=False,
            expire_on_commit=False,
        )
        return _CACHED_SESSION_FACTORY


def init_db(database_url=None):
    """Create tables for local prototypes; use migrations for shared deployments."""
    engine = get_engine(database_url)
    Base.metadata.create_all(engine)
    return engine
