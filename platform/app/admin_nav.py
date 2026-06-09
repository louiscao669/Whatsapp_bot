"""SPA navigation config for the JSON auth API."""

SPA_NAV_PAGES = [
    {"label": "Analytics", "path": "/analytics", "roles": ("admin",)},
    {"label": "QA Items", "path": "/qa-items/list", "roles": ("admin",)},
    {"label": "Review", "path": "/review-response", "roles": ("expert",)},
    {"label": "Participants", "path": "/participants", "roles": ("admin",)},
    {"label": "Export", "path": "/export/responses", "roles": ("admin",)},
]

SPA_NAV_EXPORTS = []


def nav_pages_for_role(role, pages):
    from app.services.admin_session_service import normalize_role

    normalized_role = normalize_role(role) or ""
    return [
        {"label": page["label"], "path": page["path"]}
        for page in pages
        if normalized_role in page["roles"]
    ]
