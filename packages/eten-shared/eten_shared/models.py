from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now():
    return datetime.now(timezone.utc)


def new_id():
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class AssignmentStatus(str, Enum):
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    EXPIRED = "expired"


class ResponseType(str, Enum):
    TEXT = "text"
    AUDIO = "audio"
    TRANSCRIPT = "transcript"


class ReviewStatus(str, Enum):
    PENDING = "pending"
    AUTO = "auto"
    REVIEWED = "reviewed"


class ReminderStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SessionState(str, Enum):
    ONBOARDING = "onboarding"
    IDLE = "idle"
    ASSIGNED = "assigned"
    AWAITING_RESPONSE = "awaiting_response"
    PAUSED = "paused"
    OPTED_OUT = "opted_out"


class QuestionType(str, Enum):
    OPEN = "open"
    MCQ = "mcq"
    TF = "tf"


class SourceChannel(str, Enum):
    USER_DASHBOARD = "user_dashboard"
    TELEGRAM = "telegram"
    WHATSAPP = "whatsapp"
    IMESSAGE = "imessage"
    PILOT = "pilot"


class PilotTrialStatus(str, Enum):
    """Per-question progression inside the human pilot.

    Deliberately NOT ``AssignmentStatus``: the pilot never expires a question,
    so it tracks its own three-state progression on ``pilot_question_trials``
    and leaves the shared ``assignments.status`` lifecycle (which other
    surfaces and the answer-receipt drain depend on) untouched. "Incomplete" is
    a DERIVED reporting state (``STARTED`` with no accepted answer receipt),
    never a stored status -- there is no pilot ``expired``.
    """

    ASSIGNED = "assigned"
    STARTED = "started"
    SUBMITTED = "submitted"


class OutboxStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SUPERSEDED = "superseded"


class AdminRole(str, Enum):
    ADMIN = "admin"
    EXPERT = "expert"


class AdminUser(Base):
    __tablename__ = "admin_users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(255))
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class AdminLoginCode(Base):
    __tablename__ = "admin_login_codes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    code_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class Participant(Base):
    __tablename__ = "participants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    display_name: Mapped[Optional[str]] = mapped_column(String(255))
    target_language: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    locale: Mapped[Optional[str]] = mapped_column(String(32))
    timezone: Mapped[Optional[str]] = mapped_column(String(64))
    profile_photo_uri: Mapped[Optional[str]] = mapped_column(Text)
    dashboard_preferences: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    consented: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Consent provenance. `consented` alone records only that consent exists;
    # these say when, against which approved text, and whether the person
    # actively declined (consented=False + consent_declined_at set) rather
    # than simply not having reached the screen.
    consented_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    consent_version: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    consent_declined_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    preferred_batch_size: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    completed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    nudge_platform_sequence: Mapped[list] = mapped_column(
        JSON, default=list, nullable=False
    )
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    assignments: Mapped[List["Assignment"]] = relationship(back_populates="participant")
    responses: Mapped[List["ParticipantResponse"]] = relationship(
        back_populates="participant"
    )
    events: Mapped[List["ParticipantEvent"]] = relationship(back_populates="participant")
    reminders: Mapped[List["Reminder"]] = relationship(back_populates="participant")
    badges: Mapped[List["ParticipantBadge"]] = relationship(back_populates="participant")
    wallet: Mapped[Optional["ParticipantWallet"]] = relationship(
        back_populates="participant", uselist=False
    )
    currency_events: Mapped[List["ParticipantCurrencyEvent"]] = relationship(
        back_populates="participant"
    )
    session: Mapped[Optional["ParticipantSession"]] = relationship(
        back_populates="participant", uselist=False
    )
    provider_contacts: Mapped[List["ParticipantProviderContact"]] = relationship(
        back_populates="participant",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class ParticipantProviderContact(Base):
    __tablename__ = "participant_provider_contacts"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "external_user_id",
            name="uq_participant_provider_contacts_provider_external_user_id",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    participant_id: Mapped[str] = mapped_column(
        ForeignKey("participants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # HMAC blind index of provider:chat_id -- deterministic for lookup, not
    # reversible. The readable id lives only in external_user_secret.
    external_user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    external_user_secret: Mapped[Optional[str]] = mapped_column(Text)
    identity_key_fingerprint: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(255))
    username: Mapped[Optional[str]] = mapped_column(String(255))
    first_name: Mapped[Optional[str]] = mapped_column(String(255))
    last_name: Mapped[Optional[str]] = mapped_column(String(255))
    phone: Mapped[Optional[str]] = mapped_column(String(64))
    locale: Mapped[Optional[str]] = mapped_column(String(32))
    contact_metadata: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)
    opted_in_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    opted_out_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    participant: Mapped["Participant"] = relationship(back_populates="provider_contacts")


class CommunityTeam(Base):
    __tablename__ = "community_teams"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    creator_participant_id: Mapped[str] = mapped_column(
        ForeignKey("participants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_language: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class CommunityTeamMember(Base):
    __tablename__ = "community_team_members"
    __table_args__ = (
        UniqueConstraint("participant_id", name="uq_community_team_members_participant"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    team_id: Mapped[str] = mapped_column(
        ForeignKey("community_teams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    participant_id: Mapped[str] = mapped_column(
        ForeignKey("participants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class PassageTranslation(Base):
    __tablename__ = "passage_translations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    language: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    verses: Mapped[List["PassageVerse"]] = relationship(
        back_populates="translation",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="PassageVerse.position",
    )


class PassageVerse(Base):
    __tablename__ = "passage_verses"
    __table_args__ = (
        UniqueConstraint(
            "translation_id", "verse_number", name="uq_passage_verses_translation_number"
        ),
        UniqueConstraint(
            "translation_id", "position", name="uq_passage_verses_translation_position"
        ),
        CheckConstraint("chapter_number > 0", name="passage_verses_chapter_number_positive"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    translation_id: Mapped[str] = mapped_column(
        ForeignKey("passage_translations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    verse_number: Mapped[str] = mapped_column(String(16), nullable=False)
    chapter_number: Mapped[int] = mapped_column(Integer, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    translation: Mapped["PassageTranslation"] = relationship(back_populates="verses")


class QAItem(Base):
    __tablename__ = "qa_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    passage_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    passage_reference: Mapped[Optional[str]] = mapped_column(String(255))
    passage_text: Mapped[Optional[str]] = mapped_column(Text)
    audio_url: Mapped[Optional[str]] = mapped_column(Text)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    question_type: Mapped[str] = mapped_column(
        String(16), default=QuestionType.OPEN.value, nullable=False
    )
    form_group_id: Mapped[Optional[str]] = mapped_column(String(128), index=True)
    automatic_form: Mapped[Optional[str]] = mapped_column(String(16))
    mcq_choices: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    mcq_correct_choice: Mapped[Optional[str]] = mapped_column(String(1))
    expected_answer: Mapped[str] = mapped_column(Text, nullable=False)
    required_keywords: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    optional_keywords: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    required_keyword_specs: Mapped[List[dict]] = mapped_column(JSON, default=list, nullable=False)
    optional_keyword_specs: Mapped[List[dict]] = mapped_column(JSON, default=list, nullable=False)
    original_required_keywords: Mapped[List[str]] = mapped_column(
        JSON, default=list, nullable=False
    )
    original_required_keyword_specs: Mapped[List[dict]] = mapped_column(
        JSON, default=list, nullable=False
    )
    original_question_text: Mapped[Optional[str]] = mapped_column(Text)
    original_expected_answer: Mapped[Optional[str]] = mapped_column(Text)
    original_question_type: Mapped[Optional[str]] = mapped_column(String(16))
    original_mcq_choices: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    original_mcq_correct_choice: Mapped[Optional[str]] = mapped_column(String(1))
    keyword_source: Mapped[str] = mapped_column(
        String(32), default="answer", nullable=False
    )
    min_responses_required: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    review_removed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), index=True
    )
    qa_reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), index=True
    )
    review_priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    assignments: Mapped[List["Assignment"]] = relationship(
        back_populates="qa_item",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    responses: Mapped[List["ParticipantResponse"]] = relationship(
        back_populates="qa_item",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    recordings: Mapped[List["QAItemRecording"]] = relationship(
        back_populates="qa_item",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    language_keywords: Mapped[List["QAItemLanguageKeywords"]] = relationship(
        back_populates="qa_item",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    keyword_recordings: Mapped[List["QAItemKeywordRecording"]] = relationship(
        back_populates="qa_item",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class QAItemKeywordRecording(Base):
    __tablename__ = "qa_item_keyword_recordings"
    __table_args__ = (
        UniqueConstraint(
            "qa_item_id",
            "language",
            "keyword_kind",
            "keyword_text",
            "version",
            name="uq_qa_item_keyword_recordings_version",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    qa_item_id: Mapped[str] = mapped_column(
        ForeignKey("qa_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    language: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    keyword_kind: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    keyword_text: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    storage_uri: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[Optional[str]] = mapped_column(String(128))
    uploaded_by: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    qa_item: Mapped["QAItem"] = relationship(back_populates="keyword_recordings")


class QAItemLanguageKeywords(Base):
    __tablename__ = "qa_item_language_keywords"

    qa_item_id: Mapped[str] = mapped_column(
        ForeignKey("qa_items.id", ondelete="CASCADE"), primary_key=True
    )
    language: Mapped[str] = mapped_column(String(64), primary_key=True)
    required_keywords: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    optional_keywords: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    required_keyword_specs: Mapped[List[dict]] = mapped_column(JSON, default=list, nullable=False)
    optional_keyword_specs: Mapped[List[dict]] = mapped_column(JSON, default=list, nullable=False)
    updated_by: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    qa_item: Mapped["QAItem"] = relationship(back_populates="language_keywords")


class QAItemRecording(Base):
    __tablename__ = "qa_item_recordings"
    __table_args__ = (
        UniqueConstraint(
            "qa_item_id",
            "recording_type",
            "language",
            "version",
            name="uq_qa_item_recordings_version",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    qa_item_id: Mapped[str] = mapped_column(
        ForeignKey("qa_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    recording_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    language: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    storage_uri: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[Optional[str]] = mapped_column(String(128))
    uploaded_by: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    qa_item: Mapped["QAItem"] = relationship(back_populates="recordings")


class SystemLanguage(Base):
    __tablename__ = "system_languages"

    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    seen_in_participants: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    seen_in_recordings: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class Assignment(Base):
    __tablename__ = "assignments"
    __table_args__ = (
        UniqueConstraint(
            "participant_id",
            "qa_item_id",
            name="uq_assignments_participant_qa_item",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    participant_id: Mapped[str] = mapped_column(
        ForeignKey("participants.id", ondelete="CASCADE"), nullable=False
    )
    qa_item_id: Mapped[str] = mapped_column(
        ForeignKey("qa_items.id", ondelete="CASCADE"), nullable=False
    )
    next_assignment_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("assignments.id", ondelete="SET NULL"), index=True
    )
    passage_translation_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("passage_translations.id", ondelete="SET NULL")
    )
    passage_chapter_number: Mapped[Optional[int]] = mapped_column(Integer)
    passage_verse_numbers: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    passage_text: Mapped[Optional[str]] = mapped_column(Text)
    batch_id: Mapped[Optional[str]] = mapped_column(String(36), index=True)
    status: Mapped[str] = mapped_column(
        String(32), default=AssignmentStatus.ASSIGNED.value, index=True, nullable=False
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    # When the question was actually presented / made available to the
    # participant. On the messenger this is the push (== started_at, since a
    # bot gets no "opened" signal); on the dashboard this is stamped when the
    # batch is delivered, which is EARLIER than started_at (the card being
    # opened). Lets analysis separate wait time (delivered->started) from
    # engaged time (started->completed) and gives a uniform delivered->completed
    # per-item latency across surfaces.
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    due_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    experiment_cell_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("experiment_plan_cells.id", ondelete="SET NULL"), index=True
    )

    participant: Mapped["Participant"] = relationship(back_populates="assignments")
    qa_item: Mapped["QAItem"] = relationship(back_populates="assignments")
    passage_translation: Mapped[Optional["PassageTranslation"]] = relationship()
    responses: Mapped[List["ParticipantResponse"]] = relationship(
        back_populates="assignment"
    )
    reminders: Mapped[List["Reminder"]] = relationship(
        back_populates="assignment",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    experiment_cell: Mapped[Optional["ExperimentPlanCell"]] = relationship(
        back_populates="assignments"
    )


class ExperimentPassage(Base):
    """One variant passage of a designed experiment: the (chapter x condition)
    text a participant reads. Shared across participants (56 rows for the pilot:
    7 conditions x 8 chapters). The QA is imported once per chapter as QAItems;
    only the passage varies per condition, so it lives here rather than on the
    QAItem. ``verses`` contains the experiment-specific verse segmentation;
    ``passage_text`` remains as the source snapshot. See
    DESIGNED_ASSIGNMENT_EXTENSION_2026-07-20.md.
    """

    __tablename__ = "experiment_passages"
    __table_args__ = (
        UniqueConstraint(
            "source_passage_id",
            "condition",
            "language",
            name="uq_experiment_passage_source_condition_language",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    # Stable source identity.  Luke rows are backfilled as ``luke{chapter}``;
    # tier-1 rows use ids such as ``t1_judg9``.  ``chapter`` is retained as the
    # source-passage ordinal for backwards compatibility with the first pilot.
    source_passage_id: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True, index=True
    )
    chapter: Mapped[int] = mapped_column(Integer, nullable=False)
    condition: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(128))
    language: Mapped[str] = mapped_column(String(32), nullable=False)
    passage_reference: Mapped[Optional[str]] = mapped_column(String(255))
    passage_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    plan_cells: Mapped[List["ExperimentPlanCell"]] = relationship(
        back_populates="experiment_passage"
    )
    verses: Mapped[List["ExperimentPassageVerse"]] = relationship(
        back_populates="experiment_passage",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ExperimentPassageVerse.position",
    )


class ExperimentPassageVerse(Base):
    """One numbered verse belonging to a condition-specific experiment passage."""

    __tablename__ = "experiment_passage_verses"
    __table_args__ = (
        UniqueConstraint(
            "experiment_passage_id",
            "verse_number",
            name="uq_experiment_passage_verses_number",
        ),
        UniqueConstraint(
            "experiment_passage_id",
            "position",
            name="uq_experiment_passage_verses_position",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    experiment_passage_id: Mapped[str] = mapped_column(
        ForeignKey("experiment_passages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    verse_number: Mapped[str] = mapped_column(String(16), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    experiment_passage: Mapped["ExperimentPassage"] = relationship(
        back_populates="verses"
    )


class ExperimentPlanCell(Base):
    """One Latin-square cell of a designed experiment: a participant's assigned
    condition for a single chapter. ``chapter`` selects the per-chapter QAItem
    pool; ``experiment_passage_id`` points at the variant passage the
    participant reads for this condition.

    Written once at provisioning by the plan builder; ``status`` is the only
    field the selector mutates (pending -> active -> done). Each answered
    Assignment points back here via ``Assignment.experiment_cell_id`` so the
    response export can bucket answers by condition. Null FK = a non-experiment
    (production coverage-path) assignment. See
    DESIGNED_ASSIGNMENT_EXTENSION_2026-07-20.md.
    """

    __tablename__ = "experiment_plan_cells"
    __table_args__ = (
        UniqueConstraint(
            "participant_id",
            "chapter",
            name="uq_experiment_plan_participant_chapter",
        ),
        UniqueConstraint(
            "participant_id",
            "sequence_index",
            name="uq_experiment_plan_participant_sequence",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    participant_id: Mapped[str] = mapped_column(
        ForeignKey("participants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chapter: Mapped[int] = mapped_column(Integer, nullable=False)
    condition: Mapped[str] = mapped_column(String(64), nullable=False)
    experiment_passage_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("experiment_passages.id", ondelete="SET NULL"), index=True
    )
    sequence_index: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    experiment_passage: Mapped[Optional["ExperimentPassage"]] = relationship(
        back_populates="plan_cells"
    )
    assignments: Mapped[List["Assignment"]] = relationship(
        back_populates="experiment_cell"
    )


class ExperimentWindow(Base):
    """One deliverable tier-1 three-verse window and its sole QA item.

    The unique ``(source_passage_id, window_key)`` constraint makes the study's
    one-question-per-window rule structural rather than a convention.  Eight
    balanced ``group_index`` buckets are the rows/columns rotated by the Latin
    square; a group may cross a source-passage boundary.
    """

    __tablename__ = "experiment_windows"
    __table_args__ = (
        UniqueConstraint("qa_item_id", name="uq_experiment_windows_qa_item"),
        UniqueConstraint(
            "source_passage_id",
            "window_key",
            name="uq_experiment_windows_source_window",
        ),
        UniqueConstraint("sequence_index", name="uq_experiment_windows_sequence"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    qa_item_id: Mapped[str] = mapped_column(
        ForeignKey("qa_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_passage_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    content_id: Mapped[str] = mapped_column(String(128), nullable=False)
    window_key: Mapped[str] = mapped_column(String(255), nullable=False)
    group_index: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    sequence_index: Mapped[int] = mapped_column(Integer, nullable=False)
    window_ordinals: Mapped[List[int]] = mapped_column(JSON, default=list, nullable=False)
    verse_numbers: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    qa_item: Mapped["QAItem"] = relationship()


class ParticipantResponse(Base):
    __tablename__ = "participant_responses"
    __table_args__ = (
        CheckConstraint(
            "correctness_score IS NULL OR (correctness_score >= 0 AND correctness_score <= 1)",
            name="ck_participant_responses_correctness_score",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    participant_id: Mapped[str] = mapped_column(
        ForeignKey("participants.id", ondelete="CASCADE"), nullable=False
    )
    qa_item_id: Mapped[str] = mapped_column(
        ForeignKey("qa_items.id", ondelete="CASCADE"), nullable=False
    )
    assignment_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("assignments.id", ondelete="SET NULL")
    )
    response_type: Mapped[str] = mapped_column(
        String(32), default=ResponseType.TEXT.value, nullable=False
    )
    response_text: Mapped[Optional[str]] = mapped_column(Text)
    media_id: Mapped[Optional[str]] = mapped_column(String(255))
    media_url: Mapped[Optional[str]] = mapped_column(Text)
    transcript_text: Mapped[Optional[str]] = mapped_column(Text)
    normalized_text: Mapped[Optional[str]] = mapped_column(Text)
    backtranslated_text: Mapped[Optional[str]] = mapped_column(Text)
    scoring_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    correctness_score: Mapped[Optional[float]] = mapped_column(Float)
    matched_keywords: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    missing_keywords: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    is_correct: Mapped[str] = mapped_column(
        String(32), default="pending", index=True, nullable=False
    )
    flag_reason: Mapped[Optional[str]] = mapped_column(Text)
    review_status: Mapped[str] = mapped_column(
        String(32), default=ReviewStatus.PENDING.value, index=True, nullable=False
    )
    source_channel: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    # When a correctness verdict was written (LLM judge, MCQ letter match or an
    # expert). NULL = still unscored, which the pilot export counts as missing
    # data rather than as a wrong answer. Distinct from received_at: scoring can
    # land minutes after intake, so it must never be used as a submission time.
    scored_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    participant: Mapped["Participant"] = relationship(back_populates="responses")
    qa_item: Mapped["QAItem"] = relationship(back_populates="responses")
    assignment: Mapped[Optional["Assignment"]] = relationship(back_populates="responses")


class AssignmentDelivery(Base):
    __tablename__ = "assignment_deliveries"
    __table_args__ = (
        UniqueConstraint(
            "participant_id", "provider", "provider_message_id",
            name="uq_assignment_delivery_message",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    participant_id: Mapped[str] = mapped_column(
        ForeignKey("participants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    assignment_id: Mapped[str] = mapped_column(
        ForeignKey("assignments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    provider_message_id: Mapped[str] = mapped_column(String(128), nullable=False)
    delivered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class AnswerReceipt(Base):
    __tablename__ = "answer_receipts"
    __table_args__ = (
        UniqueConstraint("assignment_id", name="uq_answer_receipts_assignment"),
        UniqueConstraint(
            "participant_id", "provider", "provider_update_id",
            name="uq_answer_receipts_provider_update",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    participant_id: Mapped[str] = mapped_column(
        ForeignKey("participants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    assignment_id: Mapped[str] = mapped_column(
        ForeignKey("assignments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    qa_item_id: Mapped[str] = mapped_column(
        ForeignKey("qa_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    provider_update_id: Mapped[str] = mapped_column(String(128), nullable=False)
    provider_question_message_id: Mapped[Optional[str]] = mapped_column(String(128))
    response_type: Mapped[str] = mapped_column(String(32), nullable=False)
    raw_answer: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default="pending", nullable=False, index=True
    )
    response_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("participant_responses.id", ondelete="SET NULL"), index=True
    )
    failure_reason: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class ParticipantEvent(Base):
    __tablename__ = "participant_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    participant_id: Mapped[str] = mapped_column(
        ForeignKey("participants.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    source: Mapped[Optional[str]] = mapped_column(String(64))
    event_metadata: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    participant: Mapped["Participant"] = relationship(back_populates="events")


class DashboardEngagementSession(Base):
    """Accumulated engaged (dwell) time on the participant dashboard.

    The dashboard front-end posts a heartbeat every ~15s while the page is
    visible. Each heartbeat advances ``active_seconds`` by the elapsed time
    since the previous heartbeat, capped so a backgrounded/closed tab cannot
    inflate dwell. One row per browser session (``session_key``). This is a
    dashboard-only metric: the messenger surfaces (Telegram/WhatsApp) expose no
    presence or dwell signal to a bot, so time-on-surface cannot be measured
    there and must not be compared cross-surface (use per-item latency and
    return-latency-after-nudge for the symmetric comparison instead).
    """

    __tablename__ = "dashboard_engagement_sessions"
    __table_args__ = (
        UniqueConstraint(
            "participant_id",
            "session_key",
            name="uq_dashboard_engagement_participant_session",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    participant_id: Mapped[str] = mapped_column(
        ForeignKey("participants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_key: Mapped[str] = mapped_column(String(64), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    last_heartbeat_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    active_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    heartbeat_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    participant: Mapped["Participant"] = relationship()


class OutboxNotification(Base):
    """Cross-surface notification queue.

    The platform (user dashboard) enqueues rows; the message-bot's background
    poller drains them and pushes messenger notifications (e.g. "answer
    recorded via dashboard"). Keeps the two processes decoupled.
    """

    __tablename__ = "outbox_notifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    participant_id: Mapped[str] = mapped_column(
        ForeignKey("participants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    notification_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default=OutboxStatus.PENDING.value, index=True, nullable=False
    )
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failure_reason: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True, nullable=False
    )
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    participant: Mapped["Participant"] = relationship()


class Reminder(Base):
    __tablename__ = "reminders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    participant_id: Mapped[str] = mapped_column(
        ForeignKey("participants.id", ondelete="CASCADE"), nullable=False
    )
    assignment_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("assignments.id", ondelete="SET NULL")
    )
    reminder_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    message_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default=ReminderStatus.PENDING.value, index=True, nullable=False
    )
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    failure_reason: Mapped[Optional[str]] = mapped_column(Text)
    delivery_metadata: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    participant: Mapped["Participant"] = relationship(back_populates="reminders")
    assignment: Mapped[Optional["Assignment"]] = relationship(back_populates="reminders")


class ParticipantBadge(Base):
    __tablename__ = "participant_badges"
    __table_args__ = (
        UniqueConstraint(
            "participant_id",
            "badge_type",
            name="uq_participant_badges_participant_badge_type",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    participant_id: Mapped[str] = mapped_column(
        ForeignKey("participants.id", ondelete="CASCADE"), nullable=False
    )
    badge_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    badge_metadata: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)
    awarded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    participant: Mapped["Participant"] = relationship(back_populates="badges")


class ParticipantWallet(Base):
    __tablename__ = "participant_wallets"
    __table_args__ = (
        UniqueConstraint("participant_id", name="uq_participant_wallets_participant"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    participant_id: Mapped[str] = mapped_column(
        ForeignKey("participants.id", ondelete="CASCADE"), nullable=False
    )
    balance: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lifetime_earned: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lifetime_spent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    participant: Mapped["Participant"] = relationship(back_populates="wallet")
    events: Mapped[List["ParticipantCurrencyEvent"]] = relationship(back_populates="wallet")


class ParticipantCurrencyEvent(Base):
    __tablename__ = "participant_currency_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    participant_id: Mapped[str] = mapped_column(
        ForeignKey("participants.id", ondelete="CASCADE"), nullable=False
    )
    wallet_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("participant_wallets.id", ondelete="SET NULL")
    )
    assignment_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("assignments.id", ondelete="SET NULL")
    )
    response_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("participant_responses.id", ondelete="SET NULL")
    )
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    source: Mapped[Optional[str]] = mapped_column(String(64))
    source_event_id: Mapped[Optional[str]] = mapped_column(String(36), index=True)
    currency_metadata: Mapped[dict] = mapped_column(
        "metadata", JSON, default=dict, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    participant: Mapped["Participant"] = relationship(back_populates="currency_events")
    wallet: Mapped[Optional["ParticipantWallet"]] = relationship(back_populates="events")


class ParticipantSession(Base):
    __tablename__ = "participant_sessions"
    __table_args__ = (
        UniqueConstraint("participant_id", name="uq_participant_sessions_participant"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    participant_id: Mapped[str] = mapped_column(
        ForeignKey("participants.id", ondelete="CASCADE"), nullable=False
    )
    current_assignment_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("assignments.id", ondelete="SET NULL")
    )
    current_batch_id: Mapped[Optional[str]] = mapped_column(String(36), index=True)
    state: Mapped[str] = mapped_column(
        String(64), default=SessionState.ONBOARDING.value, index=True, nullable=False
    )
    reminders_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    opted_out_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_prompt_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_reminder_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    session_metadata: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    participant: Mapped["Participant"] = relationship(back_populates="session")
    current_assignment: Mapped[Optional["Assignment"]] = relationship()


class PilotSession(Base):
    """One participant's run through the ``/pilot`` study interface.

    Pseudonymous by construction: it carries no personal data beyond the
    participant FK (itself an opaque id) and the consent version/timestamp the
    ethics protocol requires. One row per participant -- the pilot is a single
    sitting that may span reloads, so re-entering ``/pilot`` resumes this row
    rather than starting a new one.
    """

    __tablename__ = "pilot_sessions"
    __table_args__ = (
        UniqueConstraint("participant_id", name="uq_pilot_sessions_participant"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    participant_id: Mapped[str] = mapped_column(
        ForeignKey("participants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    consent_version: Mapped[Optional[str]] = mapped_column(String(64))
    consented_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    session_metadata: Mapped[dict] = mapped_column(
        "metadata", JSON, default=dict, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    participant: Mapped["Participant"] = relationship()
    trials: Mapped[List["PilotQuestionTrial"]] = relationship(
        back_populates="pilot_session",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class PilotQuestionTrial(Base):
    """One presented pilot question: its timing, its provenance, its outcome.

    The pilot's unit of analysis. Everything answer-shaped is *joined*, never
    copied: the answer text and ``submitted_at`` live on ``answer_receipts``
    (immutable, one per assignment), and the verdict lives on
    ``participant_responses`` (written later by the existing scoring pipeline).
    What is stored here is only what no existing table records --

      * ``active_time_ms``  -- accumulated time the question page was VISIBLE,
        measured client-side with ``performance.now()`` and pushed on
        visibility change / submit. Monotonic: a checkpoint may only raise it,
        so a stale beacon or a reload can never shrink an earlier total. This
        is the study's PRIMARY duration metric.
      * ``wall_clock_time_ms`` -- ``answer_receipts.created_at - started_at``,
        kept only as a secondary quality-control signal.
      * ``visibility_change_count`` / ``reload_count`` -- QC covariates.
      * ``status`` -- ``assigned -> started -> submitted``. Never ``expired``:
        an abandoned question stays ``started`` and is reported as incomplete
        by derivation (see :class:`PilotTrialStatus`).
      * ``trial_metadata`` -- the immutable experimental provenance snapshot
        (documented in ``eten_shared.pilot_trials.build_trial_metadata``):
        question_version, passage_id, window_key, defect_type, defect_rate and
        the plan-cell ids. Snapshotted at presentation time because QA items
        and passages are editable, so a later edit must not rewrite what a
        participant actually saw.
    """

    __tablename__ = "pilot_question_trials"
    __table_args__ = (
        UniqueConstraint("assignment_id", name="uq_pilot_trials_assignment"),
        UniqueConstraint(
            "pilot_session_id", "sequence_index", name="uq_pilot_trials_session_sequence"
        ),
        CheckConstraint("active_time_ms >= 0", name="ck_pilot_trials_active_time_ms"),
        CheckConstraint("focused_time_ms >= 0", name="ck_pilot_trials_focused_time_ms"),
        CheckConstraint(
            "passage_onscreen_ms >= 0", name="ck_pilot_trials_passage_onscreen_ms"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    pilot_session_id: Mapped[str] = mapped_column(
        ForeignKey("pilot_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    participant_id: Mapped[str] = mapped_column(
        ForeignKey("participants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    assignment_id: Mapped[str] = mapped_column(
        ForeignKey("assignments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    qa_item_id: Mapped[str] = mapped_column(
        ForeignKey("qa_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence_index: Mapped[int] = mapped_column(Integer, nullable=False)
    question_type: Mapped[str] = mapped_column(
        String(16), default=QuestionType.OPEN.value, nullable=False, index=True
    )
    condition: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(
        String(16), default=PilotTrialStatus.ASSIGNED.value, index=True, nullable=False
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    active_time_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Companion attention measures. Each is wrong in a KNOWN direction, so the
    # three together bracket real reading time rather than pretending to one
    # number: active is an upper bound (a covered window still reports
    # visible), focused is a lower bound (the address bar and OS notifications
    # steal focus mid-read), and onscreen answers the separate question of
    # whether the passage was in the viewport at all. Focus never gates
    # active_time_ms.
    focused_time_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    passage_onscreen_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    wall_clock_time_ms: Mapped[Optional[int]] = mapped_column(Integer)
    visibility_change_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    focus_change_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reload_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    submission_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    answer_receipt_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("answer_receipts.id", ondelete="SET NULL"), index=True
    )
    trial_metadata: Mapped[dict] = mapped_column(
        "metadata", JSON, default=dict, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    pilot_session: Mapped["PilotSession"] = relationship(back_populates="trials")
    participant: Mapped["Participant"] = relationship()
    assignment: Mapped["Assignment"] = relationship()
    qa_item: Mapped["QAItem"] = relationship()
    answer_receipt: Mapped[Optional["AnswerReceipt"]] = relationship()
