"""Contracts for moving pilot work off the participant's critical path.

Two changes are under test, and both are the kind whose failure is silent
rather than loud:

1. **Pre-minting.** The next question is created while the participant reads
   the current one. The hazard is not that it fails -- it is that it succeeds
   and moves ``participant_session.current_assignment_id`` to a question the
   participant has not seen. The Telegram workflow reads that pointer to decide
   which question an incoming message answers, so a moved pointer records a
   real answer against the wrong assignment, in the wrong condition, with
   nothing in the logs to say so.

2. **Deferred submit event.** The answer receipt and the trial's timing stay on
   the request; only the derived audit event follows. The hazard is a
   ``server_received_at`` taken from the background thread's clock instead of
   from the receipt, which would quietly turn an audit trail into noise.
"""

import os
import unittest
from unittest import mock

from sqlalchemy import select

from app.pilot.service import (
    _open_pilot_assignments,
    get_pilot_state,
    premint_next_assignment,
    record_submitted_event,
    submit_pilot_answer,
)
from eten_shared.domain.assignments import get_or_create_participant_session
from eten_shared.models import Assignment, ParticipantEvent, QAItem
from eten_shared.pilot_trials import QUESTION_SUBMITTED_EVENT

from test_pilot_service import PilotServiceTestCase


class PremintTests(PilotServiceTestCase):
    def setUp(self):
        super().setUp()
        # A third item, unassigned, for the pre-mint to find.
        self.spare_item = QAItem(
            passage_id="t1_luke1",
            passage_reference="1:9",
            question_text="Where did they go?",
            expected_answer="Home",
            question_type="open",
        )
        self.db.add(self.spare_item)
        self.db.flush()

    def _enable_minting(self):
        return mock.patch.dict(
            os.environ,
            {"ENABLE_AUTOMATIC_ASSIGNMENT": "true", "REQUIRE_QUESTION_AUDIO": "false"},
        )

    def _assignment_ids(self):
        return {
            row.id
            for row in self.db.scalars(
                select(Assignment).where(
                    Assignment.participant_id == self.participant.id
                )
            ).all()
        }

    def test_does_nothing_when_a_question_is_already_waiting(self):
        # The fixture leaves two open assignments: one on screen, one queued.
        # Pre-minting a third would run ahead of the plan for no benefit.
        before = self._assignment_ids()

        with self._enable_minting():
            self.assertIsNone(premint_next_assignment(self.db, self.participant.id))

        self.assertEqual(self._assignment_ids(), before)

    def test_does_nothing_when_nothing_is_on_screen(self):
        # Zero open assignments means the participant is not reading anything --
        # either they have finished or they have not started. Minting here would
        # make a completed plan look unfinished.
        for assignment in _open_pilot_assignments(self.db, self.participant):
            self.db.delete(assignment)
        self.db.flush()

        with self._enable_minting():
            self.assertIsNone(premint_next_assignment(self.db, self.participant.id))

    def test_mints_ahead_without_moving_the_messenger_pointer(self):
        self.db.delete(self.second)
        self.db.flush()

        # The participant is looking at `first`; that is where the pointer sits.
        session = get_or_create_participant_session(self.db, self.participant)
        session.current_assignment_id = self.first.id
        self.db.flush()
        before = self._assignment_ids()

        with self._enable_minting(), mock.patch(
            "app.pilot.service._select_next_dashboard_qa_item",
            return_value=(self.spare_item, None),
        ):
            minted = premint_next_assignment(self.db, self.participant.id)

        self.assertIsNotNone(minted)
        self.assertNotIn(minted.id, before)
        self.assertEqual(minted.qa_item_id, self.spare_item.id)

        # THE invariant: a question the participant has not been shown must not
        # become the one their Telegram answers are recorded against.
        self.db.refresh(session)
        self.assertEqual(session.current_assignment_id, self.first.id)

    def test_serving_a_preminted_question_moves_the_pointer_then(self):
        self.db.delete(self.second)
        self.db.flush()
        session = get_or_create_participant_session(self.db, self.participant)
        session.current_assignment_id = self.first.id
        self.db.flush()

        with self._enable_minting(), mock.patch(
            "app.pilot.service._select_next_dashboard_qa_item",
            return_value=(self.spare_item, None),
        ):
            minted = premint_next_assignment(self.db, self.participant.id)

        # Answer the current question, then ask for the next one.
        submit_pilot_answer(
            self.db,
            self.participant.id,
            self.first.id,
            submission_id="sub-1",
            answer="an answer",
            active_time_ms=1000,
            record_timing_event=False,
        )
        state = get_pilot_state(self.db, self.participant.id)

        self.assertEqual(state["question"]["assignment_id"], minted.id)
        self.db.refresh(session)
        self.assertEqual(session.current_assignment_id, minted.id)

    def test_inline_mint_serves_the_preminted_one_instead_of_a_second(self):
        """The background/inline race resolves to one question, not two."""

        self.db.delete(self.second)
        self.db.flush()

        with self._enable_minting(), mock.patch(
            "app.pilot.service._select_next_dashboard_qa_item",
            return_value=(self.spare_item, None),
        ):
            minted = premint_next_assignment(self.db, self.participant.id)
            submit_pilot_answer(
                self.db,
                self.participant.id,
                self.first.id,
                submission_id="sub-1",
                answer="an answer",
                active_time_ms=1000,
                record_timing_event=False,
            )
            state = get_pilot_state(self.db, self.participant.id)

        self.assertEqual(state["question"]["assignment_id"], minted.id)
        open_ids = {a.id for a in _open_pilot_assignments(self.db, self.participant)}
        self.assertEqual(open_ids, {minted.id})


class DeferredSubmitEventTests(PilotServiceTestCase):
    def _submitted_events(self):
        return [
            event
            for event in self.db.scalars(
                select(ParticipantEvent).where(
                    ParticipantEvent.event_type == QUESTION_SUBMITTED_EVENT
                )
            ).all()
        ]

    def test_submit_writes_no_event_when_deferred(self):
        submit_pilot_answer(
            self.db,
            self.participant.id,
            self.first.id,
            submission_id="sub-1",
            answer="an answer",
            active_time_ms=1234,
            record_timing_event=False,
        )

        self.assertEqual(self._submitted_events(), [])
        # The measurement itself is NOT deferred.
        trial = self._trial(self.first)
        self.assertEqual(trial.active_time_ms, 1234)
        self.assertIsNotNone(trial.submitted_at)

    def test_deferred_event_records_when_the_answer_was_accepted(self):
        submit_pilot_answer(
            self.db,
            self.participant.id,
            self.first.id,
            submission_id="sub-1",
            answer="an answer",
            active_time_ms=1234,
            record_timing_event=False,
        )
        trial = self._trial(self.first)

        record_submitted_event(self.db, self.participant.id, self.first.id)

        events = self._submitted_events()
        self.assertEqual(len(events), 1)
        metadata = events[0].event_metadata
        self.assertEqual(metadata["assignment_id"], self.first.id)
        self.assertEqual(metadata["active_time_ms"], 1234)
        # The clock that matters is the receipt's, not the background thread's.
        self.assertEqual(
            metadata["server_received_at"][:19],
            trial.submitted_at.isoformat()[:19],
        )

    def test_deferred_event_is_a_noop_for_an_unsubmitted_trial(self):
        get_pilot_state(self.db, self.participant.id)  # creates the trial only

        self.assertIsNone(
            record_submitted_event(self.db, self.participant.id, self.first.id)
        )
        self.assertEqual(self._submitted_events(), [])


if __name__ == "__main__":
    unittest.main()
