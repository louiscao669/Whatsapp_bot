"""Background & eligibility questionnaire on ``/pilot`` (consent -> A -> B -> C -> Q1).

Rules under test come from the IRB administration note v1.0:
Section A decides eligibility; an ineligible participant's answers are not kept
and only an anonymous count survives; B and C are optional. Section C has its own
consent prompt and completes the current survey.
"""

import json
import os
import unittest
from unittest.mock import patch

from backend import create_app
from backend.pilot.questionnaire import SCREENED_OUT_KEY, get_questionnaire_results
from eten_shared.experiment_plan import TEST_PARTICIPANT_KEY
from eten_shared.models import (
    AnswerReceipt,
    Assignment,
    Base,
    Participant,
    ParticipantSession,
    PilotQuestionnaireResponse,
    PilotQuestionTrial,
    PilotScreenoutCount,
    QAItem,
    SessionState,
)
from eten_shared.pilot_questionnaire import (
    INSTRUMENT_VERSION,
    SECTIONS,
    public_instrument,
    score_familiarity,
)
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

ELIGIBLE = {
    "a1_age_18_plus": "yes",
    "a2_first_language": "mandarin",
    "a3_reading_comfort": "comfortable",
}
ALL_CORRECT_D = {
    "d1_good_samaritan": "b",
    "d2_prodigal_son": "c",
    "d3_zacchaeus_tree": "c",
    "d4_emmaus": "b",
    "d5_lazarus": "a",
    "d6_ten_lepers": "c",
    "d7_repentant_criminal": "b",
}


class QuestionnaireTestBase(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {"PILOT_QUESTIONNAIRE_ENABLED": "1"})
        env.start()
        self.addCleanup(env.stop)

        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.factory = sessionmaker(self.engine, autoflush=False, expire_on_commit=False)
        with self.factory() as db:
            self.participant_id = self._make_participant(db, consented=True)
            db.commit()

        app = create_app()
        app.config["TESTING"] = True
        self.client = app.test_client()
        for target in (
            "backend.pilot.routes.get_session_factory",
            "backend.user_dashboard.routes.get_session_factory",
        ):
            patcher = patch(target, return_value=self.factory)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _make_participant(self, db, consented=True, test=False):
        prefs = {TEST_PARTICIPANT_KEY: True} if test else {}
        participant = Participant(
            display_name="P", consented=consented, dashboard_preferences=prefs
        )
        qa_item = QAItem(
            passage_id="t1_luke1",
            passage_reference="1:1",
            question_text="What happened?",
            expected_answer="Something",
            question_type="open",
        )
        db.add_all([participant, qa_item])
        db.flush()
        db.add_all(
            [
                Assignment(
                    participant_id=participant.id,
                    qa_item_id=qa_item.id,
                    batch_id="pilot-batch",
                    passage_text="Verse one.",
                ),
                ParticipantSession(participant_id=participant.id, state=SessionState.IDLE.value),
            ]
        )
        db.flush()
        return participant.id

    def _url(self, path, participant_id=None):
        return f"/pilot/api/{participant_id or self.participant_id}{path}"

    def _post(self, section, answers=None, participant_id=None, **extra):
        return self.client.post(
            self._url("/questionnaire", participant_id),
            json={"section": section, "answers": answers or {}, **extra},
        )

    def _confirm_exclusions(self, exclusions, participant_id=None):
        answers = {**ELIGIBLE, **exclusions}
        review = self._post("eligibility", answers, participant_id).get_json()
        self.assertEqual(review, {"status": "eligibility", "confirm_exclusions": exclusions})
        return self._post("eligibility", answers, participant_id, confirmed_exclusions=exclusions)

    def _complete(self, participant_id=None, religion_consent=False, religion=None):
        steps = [
            ("eligibility", ELIGIBLE, {}),
            ("background", {"b1_age_band": "25_34"}, {}),
            ("religion", religion or {}, {"religion_consent": religion_consent}),
        ]
        last = None
        for section, answers, extra in steps:
            last = self._post(section, answers, participant_id, **extra)
            self.assertEqual(last.status_code, 200, last.get_json())
        return last

    def _row(self, participant_id=None):
        with self.factory() as db:
            return db.scalars(
                select(PilotQuestionnaireResponse).where(
                    PilotQuestionnaireResponse.participant_id
                    == (participant_id or self.participant_id)
                )
            ).first()

    def _screenouts(self):
        with self.factory() as db:
            row = db.get(PilotScreenoutCount, INSTRUMENT_VERSION)
            return row.screenouts if row else 0


class InstrumentTests(unittest.TestCase):
    def test_public_instrument_carries_no_answer_key(self):
        payload = json.dumps(public_instrument("zh"), ensure_ascii=False)
        for marker in ("key", "correct", "score", "✓"):
            self.assertNotIn(f'"{marker}"', payload)
        self.assertNotIn("✓", payload)

    def test_only_sections_a_through_c_reach_participants(self):
        for language in ("en", "zh"):
            sections = public_instrument(language)["sections"]
            self.assertEqual([s["id"] for s in sections], ["eligibility", "background", "religion"])
            self.assertEqual([len(s["items"]) for s in sections], [3, 3, 4])
            self.assertNotIn("d1_good_samaritan", json.dumps(sections))
        for item in SECTIONS[2]["items"]:
            self.assertEqual(item["options"][-1]["code"], "prefer_not_to_say")

    def test_historical_familiarity_scoring_counts_skips_as_zero(self):
        score = score_familiarity({"d1_good_samaritan": "b", "d2_prodigal_son": "not_sure"})
        self.assertEqual(score["answered"], 2)
        self.assertEqual(score["not_sure"], 1)
        self.assertAlmostEqual(score["score"], 1 / 7)


class GateTests(QuestionnaireTestBase):
    def test_no_question_is_served_before_the_questionnaire(self):
        payload = self.client.get(self._url("/question")).get_json()
        self.assertEqual(payload["state"], "questionnaire")
        self.assertIsNone(payload["question"])
        self.assertEqual(payload["questionnaire_status"], "eligibility")
        with self.factory() as db:
            self.assertEqual(db.scalars(select(PilotQuestionTrial)).all(), [])

    def test_the_first_question_follows_a_completed_questionnaire(self):
        final = self._complete()
        self.assertEqual(final.get_json(), {"status": "complete"})
        payload = self.client.get(self._url("/question")).get_json()
        self.assertEqual(payload["state"], "question")
        self.assertIsNotNone(payload["question"])

    def test_reader_waiting_at_old_quiz_can_resume_directly_at_reading(self):
        self._complete()
        with self.factory.begin() as db:
            row = db.scalar(select(PilotQuestionnaireResponse))
            row.instrument_version = "bgq-en-v1.0-2026-08-31"
            row.completed_at = None
        state = self.client.get(self._url("/questionnaire")).get_json()
        self.assertEqual(state["status"], "complete")
        self.assertNotIn("instrument", state)
        self.assertEqual(self.client.get(self._url("/question")).get_json()["state"], "question")
        with self.factory() as db:
            report = get_questionnaire_results(db)["responses"][0]
        self.assertTrue(report["complete"])
        self.assertEqual(report["completed_at"], self._row().updated_at.isoformat())
        self.assertIsNone(report["familiarity_score"])

    def test_completed_legacy_quiz_keeps_its_original_answers_score_and_version(self):
        self._complete()
        with self.factory.begin() as db:
            row = db.scalar(select(PilotQuestionnaireResponse))
            row.instrument_version = "bgq-en-v1.0-2026-08-31"
            row.status = "familiarity"
            row.familiarity_answers = ALL_CORRECT_D
            row.familiarity_score = 1.0
        self.assertEqual(self._post("familiarity", {}).get_json(), {"status": "complete"})
        with self.factory() as db:
            report = get_questionnaire_results(db)["responses"][0]
        self.assertEqual(report["instrument_version"], "bgq-en-v1.0-2026-08-31")
        self.assertEqual(report["familiarity"], ALL_CORRECT_D)
        self.assertEqual(report["familiarity_score"], 1.0)

    def test_participants_who_already_answered_questions_are_not_sent_back(self):
        with self.factory() as db:
            assignment = db.scalars(
                select(Assignment).where(Assignment.participant_id == self.participant_id)
            ).first()
            db.add(
                AnswerReceipt(
                    participant_id=self.participant_id,
                    assignment_id=assignment.id,
                    qa_item_id=assignment.qa_item_id,
                    provider="pilot",
                    provider_update_id="legacy-1",
                    response_type="text",
                    raw_answer="x",
                )
            )
            db.commit()
        state = self.client.get(self._url("/questionnaire")).get_json()
        self.assertEqual(state["status"], "not_required")
        self.assertFalse(state["required"])
        self.assertNotEqual(self.client.get(self._url("/question")).get_json()["state"], "questionnaire")

    def test_switch_off(self):
        with patch.dict(os.environ, {"PILOT_QUESTIONNAIRE_ENABLED": "0"}):
            self.assertEqual(
                self.client.get(self._url("/questionnaire")).get_json()["status"], "not_required"
            )
            self.assertEqual(self.client.get(self._url("/question")).get_json()["state"], "question")


class FlowTests(QuestionnaireTestBase):
    def test_education_wording_and_saved_answers_follow_the_readers_instrument(self):
        for version, choice, prompt in (
            (INSTRUMENT_VERSION, "bachelors_program", "completed or are currently pursuing"),
            ("bgq-en-a-c-2026-11-13", "bachelors", "Highest level of education completed"),
        ):
            with self.subTest(version=version):
                with self.factory.begin() as db:
                    pid = self._make_participant(db)
                self._post("eligibility", ELIGIBLE, pid)
                with self.factory.begin() as db:
                    row = db.scalar(select(PilotQuestionnaireResponse).where(
                        PilotQuestionnaireResponse.participant_id == pid))
                    row.instrument_version = version
                instrument = self.client.get(self._url("/questionnaire", pid)).get_json()["instrument"]
                education = next(i for s in instrument["sections"] for i in s["items"] if i["id"] == "b2_education")
                self.assertIn(prompt, education["text"]["en"])
                self.assertIn(choice, [option["code"] for option in education["options"]])
                self.assertEqual(self._post("background", {"b2_education": choice}, pid).status_code, 200)
                self.assertEqual(self._post("religion", {}, pid, religion_consent=False).status_code, 200)
                response = self._row(pid)
                self.assertEqual(response.background_answers["b2_education"], choice)
                self.assertEqual(response.instrument_version, version)

    def test_state_lists_the_instrument_without_the_key(self):
        state = self.client.get(self._url("/questionnaire")).get_json()
        self.assertEqual(state["status"], "eligibility")
        self.assertTrue(state["required"])
        self.assertEqual(state["instrument"]["version"], INSTRUMENT_VERSION)
        self.assertEqual(state["instrument"]["language"], "en")
        self.assertNotIn('"score":', json.dumps(state))
        self.assertNotIn('"familiarity_score"', json.dumps(state))

    def test_consent_is_required_first(self):
        with self.factory() as db:
            pid = self._make_participant(db, consented=False)
            db.commit()
        response = self._post("eligibility", ELIGIBLE, pid)
        self.assertEqual(response.status_code, 400)
        self.assertIsNone(self._row(pid))

    def test_full_path_with_section_c_declined(self):
        self._complete(religion_consent=False)
        row = self._row()
        self.assertEqual(row.status, "religion")
        self.assertIsNotNone(row.completed_at)
        self.assertEqual(row.eligibility_answers["a2_first_language"], "mandarin")
        self.assertEqual(row.background_answers["b1_age_band"], "25_34")
        self.assertIsNone(row.background_answers["b2_education"])  # skipped, not invented
        self.assertIs(row.religion_consent, False)
        self.assertIsNone(row.religion_answers)
        self.assertIsNone(row.familiarity_answers)
        self.assertIsNone(row.familiarity_correct)
        self.assertIsNone(row.familiarity_answered)
        self.assertIsNone(row.familiarity_score)

    def test_section_c_answers_are_kept_when_agreed(self):
        self._complete(
            religion_consent=True,
            religion={"c1_religious_affiliation": "prefer_not_to_say", "c4_chinese_bible": "never"},
        )
        row = self._row()
        self.assertIs(row.religion_consent, True)
        self.assertEqual(row.religion_answers["c1_religious_affiliation"], "prefer_not_to_say")
        self.assertIsNone(row.religion_answers["c2_service_attendance"])
        self.assertIsNotNone(row.completed_at)
        self.assertIsNone(row.familiarity_score)

    def test_no_response_ever_reports_a_score(self):
        self._post("eligibility", ELIGIBLE)
        self._post("background", {})
        final = self._post("religion", {}, religion_consent=False)
        self.assertEqual(self._post("familiarity", ALL_CORRECT_D).get_json(), {"status": "complete"})
        self.assertIsNone(self._row().familiarity_score)
        self.assertEqual(final.get_json(), {"status": "complete"})
        self.assertNotIn('"score":', json.dumps(self.client.get(self._url("/questionnaire")).get_json()))

    def test_section_a_must_be_complete_and_valid(self):
        for answers in (
            {"a1_age_18_plus": "yes", "a2_first_language": "mandarin"},
            {**ELIGIBLE, "a3_reading_comfort": "fluent"},
            {**ELIGIBLE, "zz_extra": "1"},
        ):
            with self.subTest(answers=answers):
                self.assertEqual(self._post("eligibility", answers).status_code, 400)
        self.assertIsNone(self._row())
        self.assertEqual(self._screenouts(), 0)

    def test_sections_must_come_in_order_and_retries_do_not_overwrite(self):
        self.assertEqual(self._post("background", {}).status_code, 400)
        self._post("eligibility", ELIGIBLE)
        retry = self._post("eligibility", {**ELIGIBLE, "a3_reading_comfort": "very_comfortable"})
        self.assertEqual(retry.get_json(), {"status": "background"})
        self.assertEqual(self._row().eligibility_answers["a3_reading_comfort"], "comfortable")
        self.assertEqual(self._post("familiarity", {}).status_code, 400)

    def test_revisit_restores_and_replaces_answers_without_skipping_or_reopening(self):
        self._post("eligibility", ELIGIBLE)
        self.assertEqual(self._post("familiarity", {}, edit=True).status_code, 400)
        self._post("background", {"b1_age_band": "25_34"})
        state = self.client.get(self._url("/questionnaire")).get_json()
        self.assertEqual(state["answers"]["background"]["b1_age_band"], "25_34")
        self.assertIsNone(state["religion_consent"])
        changed = {**ELIGIBLE, "a2_first_language": "other_chinese", "a2_other_variety": "粤语"}
        self.assertEqual(self._post("eligibility", changed, edit=True).get_json()["status"], "religion")
        self._post("background", {}, edit=True)
        state = self.client.get(self._url("/questionnaire")).get_json()
        self.assertEqual(state["answers"]["eligibility"]["a2_other_variety"], "粤语")
        self.assertIsNone(state["answers"]["background"]["b1_age_band"])
        self.assertIsNone(state["religion_consent"])
        self.assertNotIn("religion", state["answers"])
        self.assertIsNone(self._row().religion_answers)
        self._post("religion", {}, religion_consent=False)
        self.assertEqual(self._post("eligibility", ELIGIBLE, edit=True).get_json(), {"status": "complete"})
        self.assertEqual(self._row().eligibility_answers["a2_other_variety"], "粤语")
        self.assertNotIn("answers", self.client.get(self._url("/questionnaire")).get_json())

    def test_edit_to_ineligible_preserves_saved_answers_until_confirmed(self):
        for test in (False, True):
            with self.factory() as db:
                pid = self._make_participant(db, test=test)
                db.commit()
            self._post("eligibility", ELIGIBLE, pid)
            self._post("background", {"b1_age_band": "25_34"}, pid)
            exclusions = {"a1_age_18_plus": "no"}
            answers = {**ELIGIBLE, **exclusions}
            before = self._screenouts()
            review = self._post("eligibility", answers, pid, edit=True).get_json()
            self.assertEqual(review, {"status": "religion", "confirm_exclusions": exclusions})
            saved = self._row(pid)
            self.assertEqual(saved.eligibility_answers["a1_age_18_plus"], "yes")
            self.assertEqual(saved.background_answers["b1_age_band"], "25_34")
            self.assertEqual(self._screenouts(), before)
            result = self._post("eligibility", answers, pid, edit=True, confirmed_exclusions=exclusions)
            self.assertEqual(result.get_json(), {"status": "screened_out", "deleted": not test})
            self.assertIsNone(self._row(pid))

    def test_section_c_needs_an_explicit_choice(self):
        self._post("eligibility", ELIGIBLE)
        self._post("background", {})
        self.assertEqual(self._post("religion", {}).status_code, 400)
        self.assertEqual(
            self._post(
                "religion", {"c1_religious_affiliation": "no_religion"}, religion_consent=False
            ).status_code,
            400,
        )

    def test_other_chinese_variety_is_eligible_and_keeps_its_text(self):
        answers = {
            **ELIGIBLE,
            "a2_first_language": "other_chinese",
            "a2_other_variety": "  粤语 ",
            "a3_reading_comfort": "somewhat_comfortable",
        }
        self.assertEqual(self._post("eligibility", answers).get_json(), {"status": "background"})
        self.assertEqual(self._row().eligibility_answers["a2_other_variety"], "粤语")

    def test_specify_text_is_dropped_when_its_option_is_not_chosen(self):
        self._post("eligibility", {**ELIGIBLE, "a2_other_variety": "粤语"})
        self.assertIsNone(self._row().eligibility_answers["a2_other_variety"])


class ScreenOutTests(QuestionnaireTestBase):
    def test_each_criterion_screens_out_only_after_confirmation(self):
        cases = (
            {"a1_age_18_plus": "no"},
            {"a2_first_language": "no"},
            {"a3_reading_comfort": "not_comfortable"},
        )
        for expected_count, exclusions in enumerate(cases, start=1):
            with self.subTest(exclusions=exclusions):
                with self.factory() as db:
                    pid = self._make_participant(db)
                    db.commit()
                answers = {**ELIGIBLE, **exclusions}
                review = self._post("eligibility", answers, pid).get_json()
                self.assertEqual(review, {"status": "eligibility", "confirm_exclusions": exclusions})
                self.assertEqual(self._screenouts(), expected_count - 1)
                self.assertIsNone(self._row(pid))
                state = self.client.get(self._url("/question", pid)).get_json()
                self.assertEqual(state["state"], "questionnaire")
                self.assertIsNone(state["question"])
                response = self._post("eligibility", answers, pid, confirmed_exclusions=exclusions)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.get_json(), {"status": "screened_out", "deleted": True})
                with self.factory() as db:
                    self.assertIsNone(db.get(Participant, pid))
                self.assertIsNone(self._row(pid))
                self.assertEqual(self._screenouts(), expected_count)
                self.assertEqual(self.client.get(self._url("/consent", pid)).status_code, 404)

    def test_all_excluding_choices_must_match_and_can_be_corrected(self):
        age = {"a1_age_18_plus": "no"}
        exclusions = {**age, "a2_first_language": "no", "a3_reading_comfort": "not_comfortable"}
        self.assertEqual(self._post("eligibility", {**ELIGIBLE, **age}).get_json()["confirm_exclusions"], age)
        for confirmation in (None, age, True, {**exclusions, "a1_age_18_plus": "yes"}):
            review = self._post("eligibility", exclusions, confirmed_exclusions=confirmation)
            self.assertEqual(review.get_json(), {"status": "eligibility", "confirm_exclusions": exclusions})
        self.assertEqual(self._post("background", {}).status_code, 400)
        state = self.client.get(self._url("/questionnaire")).get_json()
        self.assertEqual(state["status"], "eligibility")
        self.assertNotIn("answers", state)
        self.assertIsNone(self._row())
        self.assertEqual(self._post("eligibility", ELIGIBLE).get_json(), {"status": "background"})
        self.assertEqual(self._screenouts(), 0)

    def test_the_count_is_the_only_trace(self):
        self._confirm_exclusions({"a1_age_18_plus": "no"})
        with self.factory() as db:
            counts = db.scalars(select(PilotScreenoutCount)).all()
            self.assertEqual([(c.instrument_version, c.screenouts) for c in counts], [(INSTRUMENT_VERSION, 1)])
            self.assertEqual(db.scalars(select(PilotQuestionnaireResponse)).all(), [])

    def test_a_test_participant_is_flagged_not_deleted(self):
        with self.factory() as db:
            pid = self._make_participant(db, test=True)
            db.commit()
        response = self._confirm_exclusions({"a1_age_18_plus": "no"}, pid)
        self.assertEqual(response.get_json(), {"status": "screened_out", "deleted": False})
        with self.factory() as db:
            participant = db.get(Participant, pid)
            self.assertTrue(participant.dashboard_preferences[SCREENED_OUT_KEY])
            self.assertTrue(participant.dashboard_preferences[TEST_PARTICIPANT_KEY])
        self.assertIsNone(self._row(pid))
        self.assertEqual(self._screenouts(), 1)
        self.assertEqual(self.client.get(self._url("/question", pid)).get_json()["state"], "screened_out")
        self.assertEqual(self.client.get(self._url("/questionnaire", pid)).get_json()["status"], "screened_out")
        # A later submit cannot reopen it.
        self.assertEqual(self._post("eligibility", ELIGIBLE, pid).get_json(), {"status": "screened_out"})
        self.assertEqual(self._screenouts(), 1)


class ResultsTests(QuestionnaireTestBase):
    def test_admin_results_need_a_login(self):
        self.assertEqual(self.client.get("/pilot/api/questionnaire-results").status_code, 401)

    def test_results_rows_and_counts(self):
        self._complete(religion_consent=True, religion={"c2_service_attendance": "weekly"})
        with self.factory() as db:
            pid = self._make_participant(db)
            db.commit()
        self._confirm_exclusions({"a1_age_18_plus": "no"}, pid)
        with self.factory() as db:
            results = get_questionnaire_results(db)
        self.assertEqual(results["screenouts"], {INSTRUMENT_VERSION: 1})
        self.assertEqual(len(results["responses"]), 1)
        row = results["responses"][0]
        self.assertEqual(row["participant_id"], self.participant_id)
        self.assertTrue(row["complete"])
        self.assertEqual(row["religion"]["c2_service_attendance"], "weekly")
        self.assertIsNone(row["familiarity_correct"])


if __name__ == "__main__":
    unittest.main()
