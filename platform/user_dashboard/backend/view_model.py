from .achievements import achievements_view
from .community import community_view
from .contribution import contribution_view
from .journey import journey_view
from .shop import shop_view
from .sidebar import sidebar_view


def compose_dashboard_view_model(
    *,
    participant,
    wallet,
    history_summary,
    events,
    badges,
    leaderboard,
    streak,
    store,
):
    contribution = contribution_view(history_summary, events)
    community = community_view(leaderboard)
    return {
        "sidebar": sidebar_view(participant),
        "achievements_view": achievements_view(streak, badges),
        "community_view": community,
        "contribution_view": contribution,
        "journey": journey_view(history_summary),
        "shop_view": shop_view(store),
        "daily_challenge": {
            "title": "Daily challenge",
            "body": "Answer today's question batch to keep your streak active.",
        },
        "encouragements": [
            "Unlock the leadership board.",
            "Jesus loves you!",
        ],
        "lives": 0,
        "history_summary": {
            **history_summary,
            **contribution,
        },
        "leaderboard": {
            **leaderboard,
            "teams": community["team_rows"],
        },
    }
