def sidebar_view(participant):
    return {
        "display_name": participant.display_name or "Name",
        "wa_id": participant.wa_id,
    }
