def community_view(leaderboard):
    rows = list((leaderboard or {}).get("rows") or [])
    return {
        "individual_rows": rows,
        "team_rows": list((leaderboard or {}).get("teams") or []),
    }
