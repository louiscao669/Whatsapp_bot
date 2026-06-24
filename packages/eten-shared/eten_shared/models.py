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
    wa_id: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(255))
    target_language: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    locale: Mapped[Optional[str]] = mapped_column(String(32))
    timezone: Mapped[Optional[str]] = mapped_column(String(64))
    profile_photo_uri: Mapped[Optional[str]] = mapped_column(Text)
    dashboard_preferences: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    consented: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    preferred_batch_size: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    completed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
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
    batch_id: Mapped[Optional[str]] = mapped_column(String(36), index=True)
    status: Mapped[str] = mapped_column(
        String(32), default=AssignmentStatus.ASSIGNED.value, index=True, nullable=False
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    due_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    participant: Mapped["Participant"] = relationship(back_populates="assignments")
    qa_item: Mapped["QAItem"] = relationship(back_populates="assignments")
    responses: Mapped[List["ParticipantResponse"]] = relationship(
        back_populates="assignment"
    )
    reminders: Mapped[List["Reminder"]] = relationship(
        back_populates="assignment",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


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
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    participant: Mapped["Participant"] = relationship(back_populates="responses")
    qa_item: Mapped["QAItem"] = relationship(back_populates="responses")
    assignment: Mapped[Optional["Assignment"]] = relationship(back_populates="responses")


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
