def achievements_view(streak, badges):
    daily = int((streak or {}).get("current_daily_streak") or 0)
    weekly = int((streak or {}).get("current_weekly_streak") or 0)
    return {
        "daily_streak": daily,
        "weekly_streak": weekly,
        "badge_count": len(badges or []),
        "next_badge_goal": max(0, 15 - len(badges or [])),
    }
