"""HTTP-level contract for ``/pilot``, plus proof the user dashboard is intact.

Everything here goes through the real Flask app and the real blueprints; only
the session factory is redirected at an in-memory SQLite database, so routing,
status codes and response headers are exercised exactly as deployed.
"""

import unittest
from contextlib import contextmanager
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app import create_app
from eten_shared.models import (
    AnswerReceipt,
    Assignment,
    Base,
    Participant,
    ParticipantSession,
    QAItem,
    SessionState,
)


class PilotApiTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.factory = sessionmaker(self.engine, autoflush=False, expire_on_commit=False)

        with self.factory() as db:
            participant = Participant(display_name="P1", consented=True)
            other = Participant(display_name="P2", consented=True)
            qa_item = QAItem(
                passage_id="t1_luke1",
                passage_reference="1:1",
                question_text="What happened?",
                expected_answer="Something",
                question_type="open",
            )
            db.add_all([participant, other, qa_item])
            db.flush()
            assignment = Assignment(
                participant_id=participant.id,
                qa_item_id=qa_item.id,
                batch_id="pilot-batch",
                passage_text="Verse one.",
            )
            db.add_all(
                [
                    assignment,
                    ParticipantSession(
                        participant_id=participant.id, state=SessionState.IDLE.value
                    ),
                ]
            )
            db.flush()
            self.participant_id = participant.id
            self.other_id = other.id
            self.assignment_id = assignment.id
            db.commit()

        app = create_app()
        app.config["TESTING"] = True
        self.client = app.test_client()

        # Never let a test touch the configured Supabase database.
        patcher = patch("app.pilot.routes.get_session_factory", return_value=self.factory)
        patcher.start()
        self.addCleanup(patcher.stop)
        dashboard_patcher = patch(
            "app.user_dashboard.routes.get_session_factory", return_value=self.factory
        )
        dashboard_patcher.start()
        self.addCleanup(dashboard_patcher.stop)

    @contextmanager
    def _db(self):
        with self.factory() as db:
            yield db

    def _url(self, path, participant_id=None):
        return f"/pilot/api/{participant_id or self.participant_id}{path}"

    def test_every_pilot_data_endpoint_is_no_store(self):
        responses = [
            self.client.get(self._url("/question")),
            self.client.post(self._url("/session"), json={}),
            self.client.post(
                self._url("/question/viewed"), json={"assignment_id": self.assignment_id}
            ),
            self.client.post(
                self._url("/question/checkpoint"),
                json={
                    "assignment_id": self.assignment_id,
                    "event_type": "question_hidden",
                    "active_time_ms": 1200,
                },
            ),
            self.client.post(
                self._url("/answers"),
                json={
                    "assignment_id": self.assignment_id,
                    "submission_id": "sub-1",
                    "answer": "An answer",
                    "active_time_ms": 2500,
                },
            ),
            self.client.get("/pilot/api/results"),
        ]

        for response in responses:
            with self.subTest(status=response.status_code):
                self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_the_participant_page_itself_is_not_cacheable(self):
        response = self.client.get(f"/pilot/{self.participant_id}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertIn(b'id="pilot"', response.data)

    def test_versioned_static_assets_are_cacheable(self):
        response = self.client.get("/pilot/static/frontend/timing.js?v=20260818")

        self.assertEqual(response.status_code, 200)
        self.assertIn("max-age=31536000", response.headers["Cache-Control"])

    def test_full_answer_flow_over_http(self):
        state = self.client.get(self._url("/question")).get_json()
        self.assertEqual(state["state"], "question")
        self.assertEqual(state["question"]["assignment_id"], self.assignment_id)

        self.client.post(
            self._url("/question/viewed"), json={"assignment_id": self.assignment_id}
        )
        submitted = self.client.post(
            self._url("/answers"),
            json={
                "assignment_id": self.assignment_id,
                "submission_id": "sub-1",
                "answer": "An answer",
                "active_time_ms": 4200,
                "visibility_change_count": 2,
            },
        ).get_json()

        self.assertTrue(submitted["ok"])
        self.assertFalse(submitted["duplicate"])
        self.assertEqual(submitted["active_time_ms"], 4200)

        # The receipt is committed before the client is told anything, and the
        # response carries no next question -- the client must ask for it.
        self.assertNotIn("next_question", submitted)
        with self._db() as db:
            receipts = db.scalars(select(AnswerReceipt)).all()
            self.assertEqual(len(receipts), 1)

        after = self.client.get(self._url("/question")).get_json()
        self.assertEqual(after["state"], "complete")

    def test_a_retried_submission_returns_the_original_result(self):
        self.client.get(self._url("/question"))
        body = {
            "assignment_id": self.assignment_id,
            "submission_id": "sub-1",
            "answer": "An answer",
            "active_time_ms": 4200,
        }
        first = self.client.post(self._url("/answers"), json=body).get_json()
        second = self.client.post(self._url("/answers"), json=body).get_json()

        self.assertEqual(first["receipt_id"], second["receipt_id"])
        self.assertTrue(second["duplicate"])
        with self._db() as db:
            self.assertEqual(len(db.scalars(select(AnswerReceipt)).all()), 1)

    def test_another_participant_cannot_submit_this_assignment(self):
        self.client.get(self._url("/question"))
        self.client.get(self._url("/question", participant_id=self.other_id))

        response = self.client.post(
            self._url("/answers", participant_id=self.other_id),
            json={
                "assignment_id": self.assignment_id,
                "submission_id": "sub-x",
                "answer": "stolen",
                "active_time_ms": 100,
            },
        )

        self.assertEqual(response.status_code, 404)
        with self._db() as db:
            self.assertEqual(db.scalars(select(AnswerReceipt)).all(), [])

    def test_checkpoint_accepts_a_beacon_without_a_json_content_type(self):
        self.client.get(self._url("/question"))

        response = self.client.post(
            self._url("/question/checkpoint"),
            data=(
                '{"assignment_id": "%s", "event_type": "question_hidden",'
                ' "active_time_ms": 3300}' % self.assignment_id
            ),
            content_type="text/plain;charset=UTF-8",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["active_time_ms"], 3300)

    def test_results_endpoint_requires_an_admin_or_expert(self):
        response = self.client.get("/pilot/api/results")

        self.assertEqual(response.status_code, 401)

    def test_unknown_participant_is_a_404(self):
        response = self.client.get("/pilot/api/not-a-participant/question")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json()["error"], "pilot_error")


class UserDashboardStillWorksTests(PilotApiTests):
    """The pilot is additive: the existing dashboard must be untouched."""

    def test_dashboard_api_still_serves_its_payload(self):
        response = self.client.get(f"/user-dashboard/api/{self.participant_id}")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["participant"]["id"], self.participant_id)
        # Dashboard-only features the pilot deliberately omits are still there.
        self.assertIn("wallet", payload)
        self.assertIn("streak", payload)

    def test_dashboard_page_and_assets_still_serve(self):
        self.assertEqual(self.client.get("/user_dashboard/index.html").status_code, 200)
        self.assertEqual(self.client.get("/user_dashboard/styles.css").status_code, 200)
        self.assertEqual(self.client.get("/user_dashboard/login").status_code, 200)

    def test_dashboard_expiry_endpoint_still_exists(self):
        """The pilot never expires a question, but the dashboard still may."""
        response = self.client.post(
            f"/user-dashboard/api/{self.participant_id}/questions/expire",
            json={"assignment_id": self.assignment_id},
        )

        self.assertEqual(response.status_code, 200)
        with self._db() as db:
            self.assertEqual(
                db.get(Assignment, self.assignment_id).status, "expired"
            )

    def test_dashboard_heartbeat_endpoint_is_untouched_by_the_pilot(self):
        response = self.client.post(
            f"/user-dashboard/api/{self.participant_id}/heartbeat",
            json={"session_key": "abc123"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["heartbeat_count"], 1)


if __name__ == "__main__":
    unittest.main()
