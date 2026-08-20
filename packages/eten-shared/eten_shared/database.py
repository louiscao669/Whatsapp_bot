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
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS assignment_deliveries (
                id varchar(36) PRIMARY KEY,
                participant_id varchar(36) NOT NULL REFERENCES participants(id) ON DELETE CASCADE,
                assignment_id varchar(36) NOT NULL REFERENCES assignments(id) ON DELETE CASCADE,
                provider varchar(32) NOT NULL,
                provider_message_id varchar(128) NOT NULL,
                delivered_at timestamptz NOT NULL DEFAULT now(),
                CONSTRAINT uq_assignment_delivery_message
                    UNIQUE (participant_id, provider, provider_message_id)
            )
        """))
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS answer_receipts (
                id varchar(36) PRIMARY KEY,
                participant_id varchar(36) NOT NULL REFERENCES participants(id) ON DELETE CASCADE,
                assignment_id varchar(36) NOT NULL REFERENCES assignments(id) ON DELETE CASCADE,
                qa_item_id varchar(36) NOT NULL REFERENCES qa_items(id) ON DELETE CASCADE,
                provider varchar(32) NOT NULL,
                provider_update_id varchar(128) NOT NULL,
                provider_question_message_id varchar(128),
                response_type varchar(32) NOT NULL,
                raw_answer text NOT NULL,
                status varchar(32) NOT NULL DEFAULT 'pending',
                response_id varchar(36) REFERENCES participant_responses(id) ON DELETE SET NULL,
                failure_reason text,
                created_at timestamptz NOT NULL DEFAULT now(),
                processed_at timestamptz,
                CONSTRAINT uq_answer_receipts_assignment UNIQUE (assignment_id),
                CONSTRAINT uq_answer_receipts_provider_update
                    UNIQUE (participant_id, provider, provider_update_id)
            )
        """))
        for statement in (
            "CREATE INDEX IF NOT EXISTS ix_assignment_deliveries_participant_id ON assignment_deliveries(participant_id)",
            "CREATE INDEX IF NOT EXISTS ix_assignment_deliveries_assignment_id ON assignment_deliveries(assignment_id)",
            "CREATE INDEX IF NOT EXISTS ix_answer_receipts_status ON answer_receipts(status)",
            "CREATE INDEX IF NOT EXISTS ix_answer_receipts_participant_id ON answer_receipts(participant_id)",
            "CREATE INDEX IF NOT EXISTS ix_answer_receipts_assignment_id ON answer_receipts(assignment_id)",
        ):
            connection.execute(text(statement))
        connection.execute(text(
            "ALTER TABLE assignments ADD COLUMN IF NOT EXISTS "
            "next_assignment_id varchar(36) REFERENCES assignments(id) ON DELETE SET NULL"
        ))
        connection.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_assignments_next_assignment_id "
            "ON assignments (next_assignment_id)"
        ))
        connection.execute(text(
            """
            WITH ordered AS (
                SELECT id,
                       lead(id) OVER (
                           PARTITION BY participant_id ORDER BY assigned_at, id
                       ) AS next_id
                FROM assignments
            )
            UPDATE assignments AS assignment
            SET next_assignment_id = ordered.next_id
            FROM ordered
            WHERE assignment.id = ordered.id
              AND assignment.next_assignment_id IS NULL
              AND ordered.next_id IS NOT NULL
            """
        ))
        connection.execute(text(
            "ALTER TABLE qa_items ADD COLUMN IF NOT EXISTS form_group_id varchar(128)"
        ))
        connection.execute(text(
            "ALTER TABLE qa_items ADD COLUMN IF NOT EXISTS automatic_form varchar(16)"
        ))
        connection.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_qa_items_form_group_id ON qa_items (form_group_id)"
        ))
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
            text("ALTER TABLE participants ADD COLUMN IF NOT EXISTS profile_photo_uri text")
        )
        connection.execute(
            text(
                "ALTER TABLE participants ADD COLUMN IF NOT EXISTS "
                "dashboard_preferences jsonb NOT NULL DEFAULT '{}'::jsonb"
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS participant_provider_contacts (
                    id text PRIMARY KEY DEFAULT gen_random_uuid()::text,
                    participant_id text NOT NULL REFERENCES participants(id) ON DELETE CASCADE,
                    provider text NOT NULL,
                    external_user_id text NOT NULL,
                    display_name text,
                    username text,
                    first_name text,
                    last_name text,
                    phone text,
                    locale text,
                    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
                    opted_in_at timestamptz,
                    opted_out_at timestamptz,
                    last_seen_at timestamptz,
                    created_at timestamptz NOT NULL DEFAULT now(),
                    updated_at timestamptz NOT NULL DEFAULT now(),
                    CONSTRAINT uq_participant_provider_contacts_provider_external_user_id
                        UNIQUE (provider, external_user_id)
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS idx_participant_provider_contacts_participant_id
                ON participant_provider_contacts(participant_id)
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS idx_participant_provider_contacts_provider
                ON participant_provider_contacts(provider)
                """
            )
        )

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
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS participant_wallets (
                    id text PRIMARY KEY DEFAULT gen_random_uuid()::text,
                    participant_id text NOT NULL REFERENCES participants(id) ON DELETE CASCADE,
                    balance integer NOT NULL DEFAULT 0,
                    lifetime_earned integer NOT NULL DEFAULT 0,
                    lifetime_spent integer NOT NULL DEFAULT 0,
                    created_at timestamptz NOT NULL DEFAULT now(),
                    updated_at timestamptz NOT NULL DEFAULT now(),
                    CONSTRAINT uq_participant_wallets_participant UNIQUE (participant_id)
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS participant_currency_events (
                    id text PRIMARY KEY DEFAULT gen_random_uuid()::text,
                    participant_id text NOT NULL REFERENCES participants(id) ON DELETE CASCADE,
                    wallet_id text REFERENCES participant_wallets(id) ON DELETE SET NULL,
                    assignment_id text REFERENCES assignments(id) ON DELETE SET NULL,
                    response_id text REFERENCES participant_responses(id) ON DELETE SET NULL,
                    amount integer NOT NULL,
                    balance_after integer NOT NULL,
                    reason text NOT NULL,
                    source text,
                    source_event_id text,
                    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
                    created_at timestamptz NOT NULL DEFAULT now()
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS idx_participant_wallets_participant_id
                ON participant_wallets(participant_id)
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS idx_participant_currency_events_participant_id
                ON participant_currency_events(participant_id)
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS idx_participant_currency_events_reason
                ON participant_currency_events(reason)
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS idx_participant_currency_events_source_event_id
                ON participant_currency_events(source_event_id)
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS idx_participant_currency_events_created_at
                ON participant_currency_events(created_at)
                """
            )
        )

        # --- human pilot (/pilot) -------------------------------------------
        # Mirrors supabase/migrations/pilot_question_trials.sql so a deploy that
        # has not run the SQL file still comes up. See that file for the design
        # notes; the short version: pilot_question_trials is the pilot's unit of
        # analysis, it never carries an 'expired' status, and answer text /
        # submission time stay on answer_receipts rather than being copied here.
        connection.execute(
            text(
                "ALTER TABLE participant_responses ADD COLUMN IF NOT EXISTS scored_at timestamptz"
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS pilot_sessions (
                    id text PRIMARY KEY DEFAULT gen_random_uuid()::text,
                    participant_id text NOT NULL
                        REFERENCES participants(id) ON DELETE CASCADE,
                    consent_version varchar(64),
                    consented_at timestamptz,
                    started_at timestamptz NOT NULL DEFAULT now(),
                    completed_at timestamptz,
                    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
                    created_at timestamptz NOT NULL DEFAULT now(),
                    updated_at timestamptz NOT NULL DEFAULT now(),
                    CONSTRAINT uq_pilot_sessions_participant UNIQUE (participant_id)
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS pilot_question_trials (
                    id text PRIMARY KEY DEFAULT gen_random_uuid()::text,
                    pilot_session_id text NOT NULL
                        REFERENCES pilot_sessions(id) ON DELETE CASCADE,
                    participant_id text NOT NULL
                        REFERENCES participants(id) ON DELETE CASCADE,
                    assignment_id text NOT NULL
                        REFERENCES assignments(id) ON DELETE CASCADE,
                    qa_item_id text NOT NULL REFERENCES qa_items(id) ON DELETE CASCADE,
                    sequence_index integer NOT NULL,
                    question_type varchar(16) NOT NULL DEFAULT 'open',
                    condition varchar(64),
                    status varchar(16) NOT NULL DEFAULT 'assigned',
                    started_at timestamptz,
                    submitted_at timestamptz,
                    active_time_ms integer NOT NULL DEFAULT 0,
                    wall_clock_time_ms integer,
                    visibility_change_count integer NOT NULL DEFAULT 0,
                    reload_count integer NOT NULL DEFAULT 0,
                    submission_id varchar(64),
                    answer_receipt_id text
                        REFERENCES answer_receipts(id) ON DELETE SET NULL,
                    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
                    created_at timestamptz NOT NULL DEFAULT now(),
                    updated_at timestamptz NOT NULL DEFAULT now(),
                    CONSTRAINT uq_pilot_trials_assignment UNIQUE (assignment_id),
                    CONSTRAINT uq_pilot_trials_session_sequence
                        UNIQUE (pilot_session_id, sequence_index),
                    CONSTRAINT ck_pilot_trials_active_time_ms CHECK (active_time_ms >= 0),
                    CONSTRAINT ck_pilot_trials_status
                        CHECK (status IN ('assigned', 'started', 'submitted'))
                )
                """
            )
        )
        for statement in (
            "CREATE INDEX IF NOT EXISTS ix_pilot_sessions_participant_id "
            "ON pilot_sessions(participant_id)",
            "CREATE INDEX IF NOT EXISTS ix_pilot_question_trials_participant_id "
            "ON pilot_question_trials(participant_id)",
            "CREATE INDEX IF NOT EXISTS ix_pilot_question_trials_pilot_session_id "
            "ON pilot_question_trials(pilot_session_id)",
            "CREATE INDEX IF NOT EXISTS ix_pilot_question_trials_assignment_id "
            "ON pilot_question_trials(assignment_id)",
            "CREATE INDEX IF NOT EXISTS ix_pilot_question_trials_qa_item_id "
            "ON pilot_question_trials(qa_item_id)",
            "CREATE INDEX IF NOT EXISTS ix_pilot_question_trials_condition "
            "ON pilot_question_trials(condition)",
            "CREATE INDEX IF NOT EXISTS ix_pilot_question_trials_question_type "
            "ON pilot_question_trials(question_type)",
            "CREATE INDEX IF NOT EXISTS ix_pilot_question_trials_status "
            "ON pilot_question_trials(status)",
            "CREATE INDEX IF NOT EXISTS ix_pilot_question_trials_submission_id "
            "ON pilot_question_trials(submission_id)",
            "ALTER TABLE pilot_sessions ENABLE ROW LEVEL SECURITY",
            "ALTER TABLE pilot_question_trials ENABLE ROW LEVEL SECURITY",
            # Companion attention measures; see
            # supabase/migrations/pilot_attention_measures.sql.
            "ALTER TABLE pilot_question_trials ADD COLUMN IF NOT EXISTS "
            "focused_time_ms integer NOT NULL DEFAULT 0",
            "ALTER TABLE pilot_question_trials ADD COLUMN IF NOT EXISTS "
            "passage_onscreen_ms integer NOT NULL DEFAULT 0",
            "ALTER TABLE pilot_question_trials ADD COLUMN IF NOT EXISTS "
            "focus_change_count integer NOT NULL DEFAULT 0",
        ):
            connection.execute(text(statement))


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
