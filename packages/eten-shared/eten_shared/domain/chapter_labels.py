"""Passage/chapter label helpers shared across services."""


def chapter_label_from_reference(passage_reference):
    reference = (passage_reference or "").strip()
    if not reference:
        return "Other"
    if ":" in reference:
        chapter = reference.rsplit(":", 1)[0].strip()
        return chapter or reference
    return reference
