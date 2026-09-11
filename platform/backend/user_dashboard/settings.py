"""Dashboard settings services."""

from ._common import *  # noqa: F401,F403

def set_user_streak_pause(db, participant_id: str, paused: bool):
    from .profile import _participant_by_id
    from .payload import get_user_dashboard_payload

    participant = _participant_by_id(db, participant_id)
    if not participant:
        raise StreakPauseUpdateError("Participant not found")

    try:
        set_streak_pause(db, participant, paused)
    except ValueError as exc:
        raise StreakPauseUpdateError(str(exc)) from exc
    return get_user_dashboard_payload(db, participant_id)


def update_dashboard_settings(db, participant_id: str, *, language=None, batch_size=None):
    """Persist the participant's dashboard language and/or preferred batch size,
    then return the fresh dashboard payload."""
    from .profile import _participant_by_id
    from .payload import get_user_dashboard_payload

    from eten_shared.domain.batch_size_nudges import clamp_batch_size

    participant = _participant_by_id(db, participant_id)
    if not participant:
        raise DashboardSettingsError("Participant not found")

    changed = {}
    if language is not None:
        lang = str(language).strip().lower()
        if lang not in SUPPORTED_DASHBOARD_LANGUAGES:
            raise DashboardSettingsError("Unsupported language")
        preferences = dict(participant.dashboard_preferences or {})
        preferences["language"] = lang
        participant.dashboard_preferences = preferences
        changed["language"] = lang

    if batch_size is not None:
        try:
            size = clamp_batch_size(int(batch_size))
        except (TypeError, ValueError) as exc:
            raise DashboardSettingsError("Batch size must be a whole number") from exc
        participant.preferred_batch_size = size
        changed["batch_size"] = size

    if changed:
        participant.updated_at = datetime.now(timezone.utc)
        db.add(
            ParticipantEvent(
                participant_id=participant.id,
                event_type="dashboard_settings_updated",
                source="user_dashboard",
                event_metadata=changed,
            )
        )
        db.flush()

    return get_user_dashboard_payload(db, participant_id)


