"""Server-side behaviour of the ``/pilot`` study interface.

Covers the timing contract that is enforced by the server (first-view stamping,
monotonic active time, submission closing the trial), the submission
reliability contract (one receipt per assignment, cross-participant refusal),
and the reporting contract (unscored is missing data, started-and-abandoned is
incomplete, nothing ever expires).

The purely client-side half of the timing contract -- segments pausing on
hidden, resuming on visible, surviving a reload, and excluding network time --
lives in ``platform/pilot/tests/timing.test.mjs`` (``node --test``).
"""

import unittest
from datetime import timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.pilot.service import (
    PilotError,
    PilotNotFoundError,
    get_pilot_results,
    get_pilot_state,
    mark_pilot_question_viewed,
    record_pilot_activity_checkpoint,
    submit_pilot_answer,
)
from eten_shared.models import (
    AnswerReceipt,
    Assignment,
    AssignmentStatus,
    Base,
    Participant,
    ParticipantEvent,
    ParticipantResponse,
    PilotQuestionTrial,
    PilotTrialStatus,
    PassageTranslation,
    PassageVerse,
    QAItem,
    ReviewStatus,
    utc_now,
)
from eten_shared.pilot_trials import PILOT_PROVIDER


class PilotServiceTestCase(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.addCleanup(self.db.close)

        self.participant = Participant(display_name="P1", consented=True)
        self.other = Participant(display_name="P2", consented=True)
        self.open_item = QAItem(
            passage_id="t1_luke1",
            passage_reference="1:1",
            question_text="What happened first?",
            expected_answer="Something",
            question_type="open",
        )
        self.mcq_item = QAItem(
            passage_id="t1_luke1",
            passage_reference="1:4",
            question_text="Who spoke?",
            expected_answer="Mary",
            question_type="mcq",
            mcq_choices=["Mary", "Peter", "John", "Anna"],
            mcq_correct_choice="A",
        )
        self.db.add_all([self.participant, self.other, self.open_item, self.mcq_item])
        self.db.flush()

        self.first = self._assignment(self.participant, self.open_item, "Verse one text.")
        self.second = self._assignment(self.participant, self.mcq_item, "Verse four text.")
        self.db.flush()

    def _assignment(self, participant, qa_item, passage_text):
        assignment = Assignment(
            participant_id=participant.id,
            qa_item_id=qa_item.id,
            batch_id="pilot-batch",
            passage_text=passage_text,
        )
        self.db.add(assignment)
        return assignment

    def _trial(self, assignment):
        return self.db.scalars(
            select(PilotQuestionTrial).where(
                PilotQuestionTrial.assignment_id == assignment.id
            )
        ).first()

    def _events(self, event_type=None):
        stmt = select(ParticipantEvent)
        if event_type:
            stmt = stmt.where(ParticipantEvent.event_type == event_type)
        return self.db.scalars(stmt).all()

    def _score(self, assignment, *, score=None, is_correct="pending", method=None):
        """Stand in for the async scorer, which runs after receipt acceptance."""
        response = ParticipantResponse(
            participant_id=assignment.participant_id,
            qa_item_id=assignment.qa_item_id,
            assignment_id=assignment.id,
            response_text="answer",
            correctness_score=score,
            is_correct=is_correct,
            review_status=ReviewStatus.AUTO.value if score is not None else ReviewStatus.PENDING.value,
            scoring_metadata={"method": method or "backtranslation_llm_judge", "scale": "0/0.5/1"},
            scored_at=utc_now() if score is not None else None,
        )
        self.db.add(response)
        self.db.flush()
        return response


class PilotPresentationTests(PilotServiceTestCase):
    def test_presents_one_question_at_a_time_in_assignment_order(self):
        state = get_pilot_state(self.db, self.participant.id)

        self.assertEqual(state["state"], "question")
        self.assertEqual(state["question"]["assignment_id"], self.first.id)
        self.assertEqual(state["question"]["question_number"], 1)
        # No future question is exposed anywhere in the payload.
        self.assertNotIn("next_question", state)
        self.assertNotIn(self.second.id, str(state))

    def test_question_payload_reveals_no_correctness_or_reward_information(self):
        state = get_pilot_state(self.db, self.participant.id)
        payload = state["question"]

        for leak in ("expected_answer", "mcq_correct_choice", "correctness_score",
                     "is_correct", "wallet", "balance", "awards", "streak"):
            self.assertNotIn(leak, payload)
        self.assertNotIn("Something", str(payload))

    def test_presentation_creates_a_trial_without_starting_the_clock(self):
        get_pilot_state(self.db, self.participant.id)

        trial = self._trial(self.first)
        self.assertEqual(trial.status, PilotTrialStatus.ASSIGNED.value)
        self.assertIsNone(trial.started_at)
        self.assertEqual(trial.active_time_ms, 0)
        self.assertIsNone(self.first.started_at)
        # No timing event has fired: the page was never reported visible.
        self.assertEqual(self._events(), [])

    def test_mcq_question_exposes_lettered_choices(self):
        get_pilot_state(self.db, self.participant.id)
        submit_pilot_answer(
            self.db, self.participant.id, self.first.id,
            submission_id="s1", answer="text", active_time_ms=10,
        )
        state = get_pilot_state(self.db, self.participant.id)

        self.assertEqual(state["question"]["answer_mode"], "mcq")
        self.assertEqual(
            [choice["letter"] for choice in state["question"]["choices"]],
            ["A", "B", "C", "D"],
        )

    def test_completion_state_after_the_final_question(self):
        get_pilot_state(self.db, self.participant.id)
        for index, assignment in enumerate((self.first, self.second)):
            submit_pilot_answer(
                self.db, self.participant.id, assignment.id,
                submission_id=f"s{index}",
                answer="A" if assignment is self.second else "text",
                active_time_ms=1000,
            )
            get_pilot_state(self.db, self.participant.id)

        state = get_pilot_state(self.db, self.participant.id)
        self.assertEqual(state["state"], "complete")
        self.assertIsNone(state["question"])
        self.assertEqual(state["progress"]["questions_answered"], 2)


class PilotPassageRenderingTests(PilotServiceTestCase):
    """The delivered window is shown one verse per line -- but only ever by
    re-splitting the text that was actually delivered."""

    def _translation(self, verses):
        translation = PassageTranslation(language="eng", name="T")
        self.db.add(translation)
        self.db.flush()
        for position, (number, text) in enumerate(verses):
            self.db.add(
                PassageVerse(
                    translation_id=translation.id,
                    verse_number=number,
                    chapter_number=1,
                    position=position,
                    text=text,
                )
            )
        self.db.flush()
        return translation

    def test_a_joined_window_is_split_back_into_its_verses(self):
        translation = self._translation([("3", "Verse three."), ("4", "Verse four."),
                                         ("5", "Verse five.")])
        self.first.passage_translation_id = translation.id
        self.first.passage_verse_numbers = ["3", "4", "5"]
        self.first.passage_text = "Verse three. Verse four. Verse five."
        self.db.flush()

        question = get_pilot_state(self.db, self.participant.id)["question"]

        self.assertEqual(
            question["passage_lines"],
            ["Verse three.", "Verse four.", "Verse five."],
        )
        # The joined form is still reported, unchanged.
        self.assertEqual(question["passage_text"], "Verse three. Verse four. Verse five.")

    def test_a_multi_line_variant_is_split_as_delivered_without_verse_numbers(self):
        self.first.passage_verse_numbers = ["3", "4", "5"]
        self.first.passage_text = "3 Variant three.\n4 Variant four.\n5 Variant five."
        self.db.flush()

        question = get_pilot_state(self.db, self.participant.id)["question"]

        self.assertEqual(
            question["passage_lines"],
            ["Variant three.", "Variant four.", "Variant five."],
        )

    def test_a_defective_variant_is_never_replaced_by_clean_verses(self):
        """The guard that matters: an omission-condition passage must not be
        silently healed back into the full clean text just to split it."""
        translation = self._translation([("3", "Verse three."), ("4", "Verse four."),
                                         ("5", "Verse five.")])
        self.first.passage_translation_id = translation.id
        self.first.passage_verse_numbers = ["3", "4", "5"]
        # Condition variant: verse four has been omitted.
        self.first.passage_text = "Verse three. Verse five."
        self.db.flush()

        question = get_pilot_state(self.db, self.participant.id)["question"]

        self.assertEqual(question["passage_lines"], ["Verse three. Verse five."])
        self.assertNotIn("Verse four.", " ".join(question["passage_lines"]))

    def test_a_passage_with_no_verse_linkage_stays_a_single_block(self):
        question = get_pilot_state(self.db, self.participant.id)["question"]

        self.assertEqual(question["passage_lines"], ["Verse one text."])


class PilotTimingTests(PilotServiceTestCase):
    def test_first_visible_render_sets_started_at(self):
        get_pilot_state(self.db, self.participant.id)

        payload = mark_pilot_question_viewed(self.db, self.participant.id, self.first.id)

        trial = self._trial(self.first)
        self.assertTrue(payload["started_now"])
        self.assertIsNotNone(trial.started_at)
        self.assertEqual(trial.status, PilotTrialStatus.STARTED.value)
        # Server time is authoritative, and the shared assignment clock starts too.
        self.assertIsNotNone(self.first.started_at)
        self.assertEqual([e.event_type for e in self._events()], ["question_visible"])

    def test_loading_a_question_while_hidden_does_not_start_timing(self):
        # A hidden page never posts question_viewed, so nothing starts.
        get_pilot_state(self.db, self.participant.id)
        get_pilot_state(self.db, self.participant.id)

        trial = self._trial(self.first)
        self.assertIsNone(trial.started_at)
        self.assertEqual(trial.active_time_ms, 0)
        self.assertEqual(trial.status, PilotTrialStatus.ASSIGNED.value)

    def test_repeated_view_events_do_not_reset_started_at(self):
        get_pilot_state(self.db, self.participant.id)
        first = mark_pilot_question_viewed(self.db, self.participant.id, self.first.id)
        original = self._trial(self.first).started_at

        second = mark_pilot_question_viewed(self.db, self.participant.id, self.first.id)

        self.assertTrue(first["started_now"])
        self.assertFalse(second["started_now"])
        self.assertEqual(self._trial(self.first).started_at, original)
        self.assertEqual(len(self._events("question_visible")), 2)

    def test_checkpoints_only_ever_raise_accumulated_active_time(self):
        get_pilot_state(self.db, self.participant.id)
        mark_pilot_question_viewed(self.db, self.participant.id, self.first.id)

        record_pilot_activity_checkpoint(
            self.db, self.participant.id, self.first.id,
            event_type="question_hidden", active_time_ms=4200,
            visibility_change_count=1,
        )
        # A stale beacon arriving late must not shrink the total.
        record_pilot_activity_checkpoint(
            self.db, self.participant.id, self.first.id,
            event_type="question_visible", active_time_ms=900,
            visibility_change_count=2,
        )

        trial = self._trial(self.first)
        self.assertEqual(trial.active_time_ms, 4200)
        self.assertEqual(trial.visibility_change_count, 2)

    def test_checkpoint_records_auditable_visible_and_hidden_events(self):
        get_pilot_state(self.db, self.participant.id)
        mark_pilot_question_viewed(self.db, self.participant.id, self.first.id)
        record_pilot_activity_checkpoint(
            self.db, self.participant.id, self.first.id,
            event_type="question_hidden", active_time_ms=1500, visibility_change_count=1,
        )

        hidden = self._events("question_hidden")
        self.assertEqual(len(hidden), 1)
        metadata = hidden[0].event_metadata
        for field in ("participant_id", "assignment_id", "qa_item_id",
                      "client_event_at", "server_received_at",
                      "active_time_ms", "visibility_change_count"):
            self.assertIn(field, metadata)
        self.assertEqual(metadata["active_time_ms"], 1500)
        self.assertEqual(hidden[0].source, "pilot")

    def test_reload_restores_accumulated_active_time_from_the_server(self):
        get_pilot_state(self.db, self.participant.id)
        mark_pilot_question_viewed(self.db, self.participant.id, self.first.id)
        record_pilot_activity_checkpoint(
            self.db, self.participant.id, self.first.id,
            event_type="question_hidden", active_time_ms=7300, visibility_change_count=3,
        )

        # A reload re-fetches the question; the durable total comes back with it.
        reloaded = get_pilot_state(self.db, self.participant.id)["question"]

        self.assertEqual(reloaded["assignment_id"], self.first.id)
        self.assertEqual(reloaded["active_time_ms"], 7300)
        self.assertEqual(reloaded["visibility_change_count"], 3)

    def test_submission_persists_the_final_active_time_and_wall_clock(self):
        get_pilot_state(self.db, self.participant.id)
        mark_pilot_question_viewed(self.db, self.participant.id, self.first.id)
        trial = self._trial(self.first)
        trial.started_at = trial.started_at - timedelta(seconds=30)
        self.first.started_at = trial.started_at
        self.db.flush()

        payload = submit_pilot_answer(
            self.db, self.participant.id, self.first.id,
            submission_id="sub-1", answer="An answer", active_time_ms=12_000,
            visibility_change_count=2,
        )

        trial = self._trial(self.first)
        self.assertEqual(trial.status, PilotTrialStatus.SUBMITTED.value)
        self.assertEqual(trial.active_time_ms, 12_000)
        self.assertEqual(payload["active_time_ms"], 12_000)
        # Wall clock is the SECONDARY metric and is much larger than active time
        # here, exactly because hidden time counts towards it and not towards
        # active time.
        self.assertGreaterEqual(trial.wall_clock_time_ms, 29_000)
        self.assertGreater(trial.wall_clock_time_ms, trial.active_time_ms)

    def test_submitted_at_comes_from_the_answer_receipt_not_from_scoring(self):
        get_pilot_state(self.db, self.participant.id)
        mark_pilot_question_viewed(self.db, self.participant.id, self.first.id)
        submit_pilot_answer(
            self.db, self.participant.id, self.first.id,
            submission_id="sub-1", answer="An answer", active_time_ms=5_000,
        )
        receipt = self.db.scalar(
            select(AnswerReceipt).where(AnswerReceipt.assignment_id == self.first.id)
        )

        trial = self._trial(self.first)
        self.assertEqual(trial.submitted_at, receipt.created_at)

        # Scoring lands later and must move neither timestamp nor the timing.
        before = (trial.submitted_at, trial.active_time_ms, trial.wall_clock_time_ms)
        self.first.completed_at = utc_now() + timedelta(minutes=5)
        self._score(self.first, score=1.0, is_correct="yes (auto)")
        trial = self._trial(self.first)
        self.assertEqual(
            (trial.submitted_at, trial.active_time_ms, trial.wall_clock_time_ms), before
        )
        self.assertNotEqual(trial.submitted_at, self.first.completed_at)

    def test_checkpoints_after_submission_are_ignored(self):
        get_pilot_state(self.db, self.participant.id)
        mark_pilot_question_viewed(self.db, self.participant.id, self.first.id)
        submit_pilot_answer(
            self.db, self.participant.id, self.first.id,
            submission_id="sub-1", answer="An answer", active_time_ms=5_000,
        )

        payload = record_pilot_activity_checkpoint(
            self.db, self.participant.id, self.first.id,
            event_type="question_visible", active_time_ms=900_000,
        )

        self.assertFalse(payload["accepted"])
        self.assertEqual(self._trial(self.first).active_time_ms, 5_000)

    def test_focused_and_onscreen_measures_are_stored_alongside_active_time(self):
        get_pilot_state(self.db, self.participant.id)
        mark_pilot_question_viewed(self.db, self.participant.id, self.first.id)

        record_pilot_activity_checkpoint(
            self.db, self.participant.id, self.first.id,
            event_type="question_hidden",
            active_time_ms=10_000,
            focused_time_ms=7_000,
            passage_onscreen_ms=4_000,
            visibility_change_count=1,
            focus_change_count=2,
        )

        trial = self._trial(self.first)
        self.assertEqual(trial.active_time_ms, 10_000)
        self.assertEqual(trial.focused_time_ms, 7_000)
        self.assertEqual(trial.passage_onscreen_ms, 4_000)
        self.assertEqual(trial.focus_change_count, 2)
        # Focused time is a lower bound on active time, by construction.
        self.assertLessEqual(trial.focused_time_ms, trial.active_time_ms)

    def test_every_attention_measure_is_monotonic(self):
        get_pilot_state(self.db, self.participant.id)
        mark_pilot_question_viewed(self.db, self.participant.id, self.first.id)
        record_pilot_activity_checkpoint(
            self.db, self.participant.id, self.first.id,
            event_type="question_hidden", active_time_ms=9_000,
            focused_time_ms=8_000, passage_onscreen_ms=5_000, focus_change_count=3,
        )

        # A stale beacon reporting smaller totals must not shrink anything.
        record_pilot_activity_checkpoint(
            self.db, self.participant.id, self.first.id,
            event_type="question_visible", active_time_ms=100,
            focused_time_ms=50, passage_onscreen_ms=10, focus_change_count=1,
        )

        trial = self._trial(self.first)
        self.assertEqual(
            (trial.active_time_ms, trial.focused_time_ms,
             trial.passage_onscreen_ms, trial.focus_change_count),
            (9_000, 8_000, 5_000, 3),
        )

    def test_a_client_that_omits_the_new_measures_still_works(self):
        """Older clients, and beacons that only carry active time."""
        get_pilot_state(self.db, self.participant.id)
        mark_pilot_question_viewed(self.db, self.participant.id, self.first.id)

        record_pilot_activity_checkpoint(
            self.db, self.participant.id, self.first.id,
            event_type="question_hidden", active_time_ms=3_000,
        )

        trial = self._trial(self.first)
        self.assertEqual(trial.active_time_ms, 3_000)
        self.assertEqual(trial.focused_time_ms, 0)
        self.assertEqual(trial.passage_onscreen_ms, 0)

    def test_submission_persists_all_attention_measures(self):
        get_pilot_state(self.db, self.participant.id)
        mark_pilot_question_viewed(self.db, self.participant.id, self.first.id)

        payload = submit_pilot_answer(
            self.db, self.participant.id, self.first.id,
            submission_id="sub-1", answer="An answer",
            active_time_ms=12_000, focused_time_ms=9_500,
            passage_onscreen_ms=6_000, focus_change_count=4,
        )

        trial = self._trial(self.first)
        self.assertEqual(trial.focused_time_ms, 9_500)
        self.assertEqual(trial.passage_onscreen_ms, 6_000)
        self.assertEqual(trial.focus_change_count, 4)
        self.assertEqual(payload["focused_time_ms"], 9_500)

    def test_rejects_an_implausible_focused_time(self):
        get_pilot_state(self.db, self.participant.id)
        mark_pilot_question_viewed(self.db, self.participant.id, self.first.id)

        with self.assertRaises(PilotError):
            submit_pilot_answer(
                self.db, self.participant.id, self.first.id,
                submission_id="sub-1", answer="An answer",
                active_time_ms=1_000, focused_time_ms=-5,
            )

    def test_rejects_implausible_or_negative_client_timing(self):
        get_pilot_state(self.db, self.participant.id)
        mark_pilot_question_viewed(self.db, self.participant.id, self.first.id)

        for bad in (-1, "abc", 7 * 60 * 60 * 1000, None):
            with self.subTest(value=bad):
                with self.assertRaises(PilotError):
                    submit_pilot_answer(
                        self.db, self.participant.id, self.first.id,
                        submission_id="sub-1", answer="An answer", active_time_ms=bad,
                    )
        self.assertIsNone(
            self.db.scalar(
                select(AnswerReceipt).where(AnswerReceipt.assignment_id == self.first.id)
            )
        )


class PilotSubmissionTests(PilotServiceTestCase):
    def test_accepted_submission_creates_an_immutable_answer_receipt(self):
        get_pilot_state(self.db, self.participant.id)
        mark_pilot_question_viewed(self.db, self.participant.id, self.first.id)

        payload = submit_pilot_answer(
            self.db, self.participant.id, self.first.id,
            submission_id="sub-1", answer="An answer", active_time_ms=3_000,
        )

        receipt = self.db.scalar(
            select(AnswerReceipt).where(AnswerReceipt.assignment_id == self.first.id)
        )
        self.assertFalse(payload["duplicate"])
        self.assertEqual(receipt.provider, PILOT_PROVIDER)
        self.assertEqual(receipt.provider_update_id, "sub-1")
        self.assertEqual(receipt.raw_answer, "An answer")
        self.assertEqual(receipt.status, "pending")
        # Scoring has NOT happened yet -- it runs after receipt acceptance.
        self.assertIsNone(receipt.response_id)
        self.assertEqual(self.db.scalars(select(ParticipantResponse)).all(), [])

    def test_duplicate_submission_id_returns_the_original_result(self):
        get_pilot_state(self.db, self.participant.id)
        mark_pilot_question_viewed(self.db, self.participant.id, self.first.id)
        first = submit_pilot_answer(
            self.db, self.participant.id, self.first.id,
            submission_id="sub-1", answer="An answer", active_time_ms=3_000,
        )

        again = submit_pilot_answer(
            self.db, self.participant.id, self.first.id,
            submission_id="sub-1", answer="A different answer", active_time_ms=99_000,
        )

        self.assertTrue(again["duplicate"])
        self.assertEqual(again["receipt_id"], first["receipt_id"])
        self.assertEqual(again["active_time_ms"], first["active_time_ms"])
        receipts = self.db.scalars(
            select(AnswerReceipt).where(AnswerReceipt.assignment_id == self.first.id)
        ).all()
        self.assertEqual(len(receipts), 1)
        self.assertEqual(receipts[0].raw_answer, "An answer")

    def test_a_second_submission_id_still_yields_one_receipt(self):
        """A retry that lost its id must not create a second response."""
        get_pilot_state(self.db, self.participant.id)
        submit_pilot_answer(
            self.db, self.participant.id, self.first.id,
            submission_id="sub-1", answer="An answer", active_time_ms=3_000,
        )

        again = submit_pilot_answer(
            self.db, self.participant.id, self.first.id,
            submission_id="sub-2", answer="An answer", active_time_ms=3_000,
        )

        self.assertTrue(again["duplicate"])
        self.assertEqual(
            len(self.db.scalars(
                select(AnswerReceipt).where(AnswerReceipt.assignment_id == self.first.id)
            ).all()),
            1,
        )

    def test_open_and_mcq_submissions_both_work(self):
        get_pilot_state(self.db, self.participant.id)
        submit_pilot_answer(
            self.db, self.participant.id, self.first.id,
            submission_id="open-1", answer="Free text answer", active_time_ms=1_000,
        )
        get_pilot_state(self.db, self.participant.id)
        submit_pilot_answer(
            self.db, self.participant.id, self.second.id,
            submission_id="mcq-1", answer="b", active_time_ms=2_000,
        )

        receipts = {
            r.assignment_id: r for r in self.db.scalars(select(AnswerReceipt)).all()
        }
        self.assertEqual(receipts[self.first.id].raw_answer, "Free text answer")
        self.assertEqual(receipts[self.second.id].raw_answer, "B")
        self.assertEqual(self._trial(self.second).question_type, "mcq")

    def test_mcq_rejects_an_answer_that_is_not_a_choice(self):
        get_pilot_state(self.db, self.participant.id)
        submit_pilot_answer(
            self.db, self.participant.id, self.first.id,
            submission_id="open-1", answer="text", active_time_ms=10,
        )
        get_pilot_state(self.db, self.participant.id)

        with self.assertRaises(PilotError):
            submit_pilot_answer(
                self.db, self.participant.id, self.second.id,
                submission_id="mcq-1", answer="probably Mary", active_time_ms=10,
            )

    def test_participant_cannot_touch_another_participants_assignment(self):
        get_pilot_state(self.db, self.participant.id)
        get_pilot_state(self.db, self.other.id)

        for call in (
            lambda: submit_pilot_answer(
                self.db, self.other.id, self.first.id,
                submission_id="sub-x", answer="stolen", active_time_ms=10,
            ),
            lambda: mark_pilot_question_viewed(self.db, self.other.id, self.first.id),
            lambda: record_pilot_activity_checkpoint(
                self.db, self.other.id, self.first.id,
                event_type="question_hidden", active_time_ms=10,
            ),
        ):
            with self.subTest(call=call):
                with self.assertRaises(PilotNotFoundError):
                    call()

        self.assertIsNone(
            self.db.scalar(
                select(AnswerReceipt).where(AnswerReceipt.assignment_id == self.first.id)
            )
        )


class PilotNeverExpiresTests(PilotServiceTestCase):
    def test_an_abandoned_question_stays_started_and_is_never_expired(self):
        get_pilot_state(self.db, self.participant.id)
        mark_pilot_question_viewed(self.db, self.participant.id, self.first.id)

        # Participant walks away; time passes; they come back.
        state = get_pilot_state(self.db, self.participant.id)

        trial = self._trial(self.first)
        self.assertEqual(trial.status, PilotTrialStatus.STARTED.value)
        self.assertNotEqual(trial.status, "expired")
        self.assertEqual(self.first.status, AssignmentStatus.ASSIGNED.value)
        # Still the same question -- nothing was skipped past.
        self.assertEqual(state["question"]["assignment_id"], self.first.id)

    def test_no_pilot_trial_can_hold_an_expired_status(self):
        get_pilot_state(self.db, self.participant.id)
        statuses = {status.value for status in PilotTrialStatus}
        self.assertEqual(statuses, {"assigned", "started", "submitted"})
        self.assertNotIn("expired", statuses)


class PilotResultsTests(PilotServiceTestCase):
    def _answer(self, assignment, answer, submission_id, active_ms):
        get_pilot_state(self.db, self.participant.id)
        mark_pilot_question_viewed(self.db, self.participant.id, assignment.id)
        return submit_pilot_answer(
            self.db, self.participant.id, assignment.id,
            submission_id=submission_id, answer=answer, active_time_ms=active_ms,
        )

    def test_started_but_unanswered_question_is_reported_incomplete(self):
        get_pilot_state(self.db, self.participant.id)
        mark_pilot_question_viewed(self.db, self.participant.id, self.first.id)

        overall = get_pilot_results(self.db)["overall"]

        self.assertEqual(overall["questions_presented"], 1)
        self.assertEqual(overall["questions_started"], 1)
        self.assertEqual(overall["questions_answered"], 0)
        self.assertEqual(overall["questions_incomplete"], 1)
        self.assertEqual(overall["completion_rate"], 0.0)

    def test_unscored_responses_are_excluded_from_accuracy_denominators(self):
        self._answer(self.first, "Free text", "open-1", 1_000)
        self._answer(self.second, "A", "mcq-1", 2_000)
        # Only the open answer has been judged so far.
        self._score(self.first, score=1.0, is_correct="yes (auto)")

        overall = get_pilot_results(self.db)["overall"]

        self.assertEqual(overall["questions_answered"], 2)
        self.assertEqual(overall["open_count"], 1)
        self.assertEqual(overall["open_scored_count"], 1)
        self.assertEqual(overall["open_unscored"], 0)
        self.assertEqual(overall["accuracy_open"], 1.0)
        self.assertEqual(overall["mcq_count"], 1)
        self.assertEqual(overall["mcq_scored_count"], 0)
        self.assertEqual(overall["mcq_unscored"], 1)
        # Zero scored MCQ => no accuracy at all, NOT 0.0.
        self.assertIsNone(overall["accuracy_mcq"])
        self.assertEqual(overall["correct_mcq"], 0)

    def test_half_credit_open_answers_count_in_the_mean_but_not_as_correct(self):
        self._answer(self.first, "Partly right", "open-1", 1_000)
        self._score(self.first, score=0.5, is_correct="partial (auto)")

        overall = get_pilot_results(self.db)["overall"]

        self.assertEqual(overall["open_scored_count"], 1)
        self.assertEqual(overall["correct_open"], 0)
        self.assertEqual(overall["accuracy_open"], 0.0)
        self.assertEqual(overall["open_score_mean"], 0.5)

    def test_mcq_scored_at_intake_without_a_numeric_score_still_counts(self):
        """The existing MCQ pipeline records only a label at intake."""
        self.db.delete(self.first)  # an MCQ-only run
        self.db.flush()
        self._answer(self.second, "A", "mcq-1", 2_000)
        self._score(self.second, score=None, is_correct="yes (auto)", method="exact_letter")

        overall = get_pilot_results(self.db)["overall"]

        self.assertEqual(overall["mcq_scored_count"], 1)
        self.assertEqual(overall["correct_mcq"], 1)
        self.assertEqual(overall["accuracy_mcq"], 1.0)

    def test_report_breaks_results_down_by_every_required_dimension(self):
        self._answer(self.first, "Free text", "open-1", 1_000)
        self._answer(self.second, "A", "mcq-1", 3_000)
        self._score(self.first, score=1.0, is_correct="yes (auto)")

        report = get_pilot_results(self.db)

        self.assertEqual(
            set(report),
            {"overall", "by_participant", "by_condition", "by_question_type",
             "by_question", "trials"},
        )
        self.assertEqual(len(report["by_participant"]), 1)
        self.assertEqual(report["by_participant"][0]["participant_id"], self.participant.id)
        self.assertEqual(
            {row["question_type"] for row in report["by_question_type"]}, {"open", "mcq"}
        )
        self.assertEqual(len(report["by_question"]), 2)

        for block in ("focused_time_ms", "passage_onscreen_ms",
                      "focused_time_ms_open", "focused_time_ms_mcq"):
            self.assertIn(block, report["overall"])
        timing = report["overall"]["active_time_ms"]
        self.assertEqual(timing["n"], 2)
        self.assertEqual(timing["median"], 2_000)
        self.assertEqual(timing["p25"], 1_500)
        self.assertEqual(timing["p75"], 2_500)
        self.assertEqual(report["overall"]["active_time_ms_open"]["median"], 1_000)
        self.assertEqual(report["overall"]["active_time_ms_mcq"]["median"], 3_000)

    def test_trial_rows_carry_the_full_provenance_chain(self):
        self._answer(self.first, "Free text", "open-1", 1_000)

        row = get_pilot_results(self.db)["trials"][0]

        for field in (
            "assignment_id", "participant_id", "pilot_session_id", "qa_item_id",
            "question_version", "question_type", "sequence_index", "condition",
            "defect_type", "defect_rate", "passage_id", "window_key",
            "started_at", "submitted_at", "active_time_ms", "wall_clock_time_ms",
            "visibility_change_count", "reload_count", "status", "submission_id",
            "raw_answer", "selected_choice", "correctness_score", "is_correct",
            "scoring_method", "scoring_version", "scored_at",
        ):
            self.assertIn(field, row)
        self.assertEqual(row["assignment_id"], self.first.id)
        self.assertEqual(row["passage_id"], "t1_luke1")
        self.assertEqual(row["raw_answer"], "Free text")
        self.assertTrue(row["question_version"])

    def test_no_aggregate_is_written_back_onto_the_participant(self):
        self._answer(self.first, "Free text", "open-1", 1_000)
        get_pilot_results(self.db)

        # completed_count is the dashboard's mutable counter; the pilot never
        # touches it, and accuracy lives nowhere but the query.
        self.assertEqual(self.participant.completed_count, 0)


if __name__ == "__main__":
    unittest.main()
