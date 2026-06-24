def community_view(leaderboard):
    rows = list((leaderboard or {}).get("rows") or [])
    return {
        "individual_rows": rows,
        "team_rows": _team_rows_from_individuals(rows),
    }


def _team_rows_from_individuals(rows):
    teams = []
    for index in range(0, len(rows), 2):
        members = rows[index:index + 2]
        if not members:
            continue
        teams.append(
            {
                "rank": len(teams) + 1,
                "team_id": f"team-{len(teams) + 1}",
                "display_name": f"Team {len(teams) + 1}",
                "weekly_earned": sum(int(member.get("weekly_earned") or 0) for member in members),
                "members": [member.get("participant_id") for member in members],
            }
        )
    return teams
