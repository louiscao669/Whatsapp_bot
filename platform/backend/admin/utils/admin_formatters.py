from datetime import timezone


def format_display_datetime(value, *, label="UTC"):
    """Human-readable timestamp with an explicit timezone label."""
    if not value:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    utc_value = value.astimezone(timezone.utc)
    formatted = utc_value.strftime("%Y-%m-%d : %H:%M:%S")
    return f"{formatted} {label}" if label else formatted


def format_correctness_score(value):
    if value is None:
        return ""
    return f"{round(float(value), 3):.3f}"
