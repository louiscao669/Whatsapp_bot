"""Dashboard community services."""

from ._common import *  # noqa: F401,F403

def _week_bounds(now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)
    week_start = (now - timedelta(days=now.weekday())).replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    return week_start, week_start + timedelta(days=7)


def _display_name_for_leaderboard(participant, fallback_index):
    name = (participant.display_name or "").strip()
    if name:
        return name
    return f"Participant {fallback_index}"


def _language_code(participant):
    return (participant.target_language or "unknown").strip() or "unknown"


def _normalized_team_name(name):
    value = " ".join(str(name or "").split())
    if not value:
        raise CommunityTeamError("Team name is required")
    if len(value) > 64:
        raise CommunityTeamError("Team name must be 64 characters or fewer")
    return value


def _participant_team_membership(db, participant_id):
    return db.scalar(
        select(CommunityTeamMember).where(
            CommunityTeamMember.participant_id == participant_id
        )
    )


def create_community_team(db, participant_id, name):
    from .profile import _participant_by_id
    from .payload import get_user_dashboard_payload

    participant = _participant_by_id(db, participant_id)
    if not participant:
        raise CommunityTeamError("Participant not found")
    if _participant_team_membership(db, participant.id):
        raise CommunityTeamError("You are already on a team")
    name = _normalized_team_name(name)
    existing = db.scalar(
        select(CommunityTeam).where(func.lower(CommunityTeam.name) == name.lower())
    )
    if existing:
        raise CommunityTeamError("A team with that name already exists")

    team = CommunityTeam(
        name=name,
        creator_participant_id=participant.id,
        target_language=participant.target_language,
    )
    db.add(team)
    db.flush()
    db.add(CommunityTeamMember(team_id=team.id, participant_id=participant.id))
    db.flush()
    return get_user_dashboard_payload(db, participant.id)


def join_community_team(db, participant_id, team_id):
    from .profile import _participant_by_id
    from .payload import get_user_dashboard_payload

    participant = _participant_by_id(db, participant_id)
    if not participant:
        raise CommunityTeamError("Participant not found")
    if _participant_team_membership(db, participant.id):
        raise CommunityTeamError("You are already on a team")
    team = db.scalar(
        select(CommunityTeam).where(CommunityTeam.id == str(team_id or "")).with_for_update()
    )
    if not team:
        raise CommunityTeamError("Team not found")
    if team.target_language != participant.target_language:
        raise CommunityTeamError("You can only join a team in your language community")
    member_count = db.scalar(
        select(func.count(CommunityTeamMember.id)).where(
            CommunityTeamMember.team_id == team.id
        )
    )
    if int(member_count or 0) >= TEAM_MAX_MEMBERS:
        raise CommunityTeamError("This team already has 4 members")
    db.add(CommunityTeamMember(team_id=team.id, participant_id=participant.id))
    db.flush()
    return get_user_dashboard_payload(db, participant.id)


def rename_community_team(db, participant_id, team_id, name):
    from .payload import get_user_dashboard_payload

    team = db.scalar(select(CommunityTeam).where(CommunityTeam.id == str(team_id or "")))
    if not team:
        raise CommunityTeamError("Team not found")
    if team.creator_participant_id != participant_id:
        raise CommunityTeamError("Only the team creator can change its name")
    name = _normalized_team_name(name)
    existing = db.scalar(
        select(CommunityTeam).where(
            func.lower(CommunityTeam.name) == name.lower(),
            CommunityTeam.id != team.id,
        )
    )
    if existing:
        raise CommunityTeamError("A team with that name already exists")
    team.name = name
    team.updated_at = datetime.now(timezone.utc)
    db.flush()
    return get_user_dashboard_payload(db, participant_id)


def leave_community_team(db, participant_id, team_id):
    from .payload import get_user_dashboard_payload

    membership = db.scalar(
        select(CommunityTeamMember).where(
            CommunityTeamMember.team_id == str(team_id or ""),
            CommunityTeamMember.participant_id == participant_id,
        )
    )
    if not membership:
        raise CommunityTeamError("You are not a member of this team")
    team = db.scalar(select(CommunityTeam).where(CommunityTeam.id == membership.team_id))
    if team and team.creator_participant_id == participant_id:
        raise CommunityTeamError("Team creators must remove the team instead of leaving it")
    db.delete(membership)
    db.flush()
    return get_user_dashboard_payload(db, participant_id)


def remove_community_team(db, participant_id, team_id):
    from .payload import get_user_dashboard_payload

    team = db.scalar(select(CommunityTeam).where(CommunityTeam.id == str(team_id or "")))
    if not team:
        raise CommunityTeamError("Team not found")
    if team.creator_participant_id != participant_id:
        raise CommunityTeamError("Only the team creator can remove the team")
    # Explicit deletion keeps this operation correct in SQLite tests as well as
    # PostgreSQL, where the foreign key also cascades team membership deletion.
    db.execute(
        delete(CommunityTeamMember).where(CommunityTeamMember.team_id == team.id)
    )
    db.delete(team)
    db.flush()
    return get_user_dashboard_payload(db, participant_id)


def get_language_team_leaderboard(db, participant, week_start, week_end):
    teams = db.scalars(
        select(CommunityTeam)
        .where(CommunityTeam.target_language == participant.target_language)
        .order_by(CommunityTeam.created_at.asc())
    ).all()
    if not teams:
        return []
    team_ids = [team.id for team in teams]
    memberships = db.execute(
        select(CommunityTeamMember, Participant)
        .join(Participant, Participant.id == CommunityTeamMember.participant_id)
        .where(CommunityTeamMember.team_id.in_(team_ids))
        .order_by(CommunityTeamMember.joined_at.asc())
    ).all()
    member_ids = [member.participant_id for member, _ in memberships]
    scores = {}
    if member_ids:
        scores = {
            participant_id: int(score or 0)
            for participant_id, score in db.execute(
                select(
                    ParticipantCurrencyEvent.participant_id,
                    func.coalesce(func.sum(ParticipantCurrencyEvent.amount), 0),
                )
                .where(
                    ParticipantCurrencyEvent.participant_id.in_(member_ids),
                    ParticipantCurrencyEvent.created_at >= week_start,
                    ParticipantCurrencyEvent.created_at < week_end,
                    ParticipantCurrencyEvent.amount > 0,
                )
                .group_by(ParticipantCurrencyEvent.participant_id)
            ).all()
        }
    members_by_team = {team_id: [] for team_id in team_ids}
    for membership, member_participant in memberships:
        members_by_team[membership.team_id].append(
            {
                "participant_id": member_participant.id,
                "display_name": _display_name_for_leaderboard(member_participant, 0),
            }
        )
    rows = [
        {
            "team_id": team.id,
            "display_name": team.name,
            "weekly_earned": sum(
                scores.get(member["participant_id"], 0)
                for member in members_by_team[team.id]
            ),
            "members": members_by_team[team.id],
            "member_ids": [member["participant_id"] for member in members_by_team[team.id]],
            "member_count": len(members_by_team[team.id]),
            "is_current_user": any(
                member["participant_id"] == participant.id
                for member in members_by_team[team.id]
            ),
            "is_creator": team.creator_participant_id == participant.id,
        }
        for team in teams
    ]
    rows.sort(key=lambda row: (-row["weekly_earned"], row["display_name"].lower()))
    previous_score = None
    rank = 0
    for index, row in enumerate(rows, start=1):
        if previous_score is None or row["weekly_earned"] < previous_score:
            rank = index
        row["rank"] = rank
        previous_score = row["weekly_earned"]
    return rows


def get_language_weekly_leaderboard(db, participant, limit=LEADERBOARD_LIMIT):
    from .serialization import _iso_datetime

    language = _language_code(participant)
    week_start, week_end = _week_bounds()
    weekly_score = func.coalesce(func.sum(ParticipantCurrencyEvent.amount), 0).label(
        "weekly_score"
    )
    rows = db.execute(
        select(Participant, weekly_score)
        .join(
            ParticipantCurrencyEvent,
            ParticipantCurrencyEvent.participant_id == Participant.id,
        )
        .where(
            Participant.target_language == participant.target_language,
            ParticipantCurrencyEvent.created_at >= week_start,
            ParticipantCurrencyEvent.created_at < week_end,
            ParticipantCurrencyEvent.amount > 0,
        )
        .group_by(Participant.id)
        .order_by(weekly_score.desc(), Participant.created_at.asc())
    ).all()

    leaderboard_rows = []
    current_user_row = None
    previous_score = None
    current_rank = 0
    for index, (row_participant, score) in enumerate(rows, start=1):
        score = int(score or 0)
        if previous_score is None or score < previous_score:
            current_rank = index
        previous_score = score

        row = {
            "rank": current_rank,
            "participant_id": row_participant.id,
            "display_name": _display_name_for_leaderboard(row_participant, index),
            "weekly_earned": score,
            "is_current_user": row_participant.id == participant.id,
        }
        if len(leaderboard_rows) < limit:
            leaderboard_rows.append(row)
        if row["is_current_user"]:
            current_user_row = row

    if current_user_row is None:
        current_user_row = {
            "rank": None,
            "participant_id": participant.id,
            "display_name": _display_name_for_leaderboard(
                participant,
                len(rows) + 1,
            ),
            "weekly_earned": 0,
            "is_current_user": True,
        }

    return {
        "scope": "language",
        "language": language,
        "week_start": _iso_datetime(week_start),
        "week_end": _iso_datetime(week_end),
        "limit": limit,
        "current_user": current_user_row,
        "rows": leaderboard_rows,
        "teams": get_language_team_leaderboard(db, participant, week_start, week_end),
    }


