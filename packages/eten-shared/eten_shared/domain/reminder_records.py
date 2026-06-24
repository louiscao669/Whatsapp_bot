"""Provider-neutral reminder record hook.

Concrete providers own reminder cadence and template policy.
"""


def create_assignment_reminders(db, assignment, participant):
    return []
