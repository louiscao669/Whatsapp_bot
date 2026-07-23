"""Experiment passage (pilot condition variant) list + detail for the admin UI.

These condition-specific variants are written by ``pilot_import.py`` into
``experiment_passages`` with owned ``experiment_passage_verses`` children.
"""

from sqlalchemy import select

from eten_shared.models import ExperimentPassage


def _summary(row: ExperimentPassage) -> dict:
    return {
        "id": row.id,
        "chapter": row.chapter,
        "condition": row.condition,
        "name": row.name,
        "language": row.language,
        "passage_reference": row.passage_reference,
        "char_count": len(row.passage_text or ""),
        "verse_count": len(row.verses),
    }


def list_experiment_passages(db) -> list[dict]:
    rows = db.scalars(
        select(ExperimentPassage).order_by(
            ExperimentPassage.chapter,
            ExperimentPassage.condition,
            ExperimentPassage.language,
        )
    ).all()
    return [_summary(row) for row in rows]


def get_experiment_passage(db, passage_id: str):
    row = db.get(ExperimentPassage, passage_id)
    if row is None:
        return None
    return {
        **_summary(row),
        "passage_text": row.passage_text,
        "verses": [
            {
                "verse_number": verse.verse_number,
                "position": verse.position,
                "text": verse.text,
            }
            for verse in row.verses
        ],
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
