def sidebar_view(participant):
    return {
        "display_name": participant.display_name or "Name",
        "participant_id": participant.id,
    }
