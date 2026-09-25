"""Admin "Create test participant": service, HTTP routes, and exclusion from real data."""

import sys
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker

from backend import create_app
from backend.admin.services.participants_api_service import (
    get_participant_detail,
    list_participants_dashboard,
)
from backend.admin.services.test_participants_service import (
    TestParticipantError,
    create_test_participant,
    delete_test_participant,
)
from eten_shared.experiment_plan import (
    SLOTS,
    TEST_PARTICIPANT_KEY,
    build_cells,
    is_test_participant,
)
from eten_shared.models import (
    Assignment,
    AssignmentStatus,
    Base,
    ExperimentPassage,
    ExperimentPlanCell,
    ExperimentWindow,
    Participant,
    ParticipantResponse,
    QAItem,
)
from eten_shared.repo_paths import REPO_ROOT


def _engine():
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_connection, _record):  # SQLite ignores ON DELETE CASCADE otherwise
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    return engine


def _import_legacy_passages(db, language="zh"):
    for chapter in range(1, 9):
        for condition in set(SLOTS):
            db.add(ExperimentPassage(
                chapter=chapter, condition=condition, language=language,
                passage_text=f"ch{chapter} {condition}",
            ))
    db.flush()


class TestParticipantServiceTests(unittest.TestCase):
    def setUp(self):
        self.engine = _engine()
        self.factory = sessionmaker(self.engine, autoflush=False, expire_on_commit=False)

    def test_creates_flagged_unconsented_participant_with_full_plan(self):
        with self.factory() as db:
            _import_legacy_passages(db)
            result = create_test_participant(db, display_name="gold72 check")
            db.commit()

            participant = db.get(Participant, result["participant_id"])
            self.assertTrue(is_test_participant(participant))
            self.assertFalse(participant.consented)
            self.assertEqual(participant.target_language, "zh")
            self.assertEqual(participant.display_name, "TEST gold72 check")
            self.assertEqual(result["pilot_path"], f"/pilot/{participant.id}")

            cells = db.scalars(select(ExperimentPlanCell).where(
                ExperimentPlanCell.participant_id == participant.id)).all()
            self.assertEqual(len(cells), 8)
            self.assertEqual(sorted(c.condition for c in cells), sorted(SLOTS))
            self.assertTrue(all(c.experiment_passage_id for c in cells))
            # identical to what the CLI would write for this block
            expected = build_cells(participant.id, result["block_index"])
            self.assertEqual(
                sorted((c.chapter, c.condition, c.sequence_index) for c in cells),
                sorted(expected),
            )
            self.assertEqual([p["sequence_index"] for p in result["plan"]], list(range(8)))

    def test_default_name_is_marked_test(self):
        with self.factory() as db:
            _import_legacy_passages(db)
            result = create_test_participant(db, display_name="  ")
            self.assertTrue(result["display_name"].startswith("TEST "))
            result = create_test_participant(db, display_name="test run")
            self.assertEqual(result["display_name"], "test run")

    def test_block_index_rotates_across_test_participants(self):
        with self.factory() as db:
            _import_legacy_passages(db)
            db.add(Participant(display_name="real", consented=True))  # not counted
            db.flush()
            blocks = [create_test_participant(db)["block_index"] for _ in range(9)]
            self.assertEqual(blocks, [0, 1, 2, 3, 4, 5, 6, 7, 0])

    def test_refuses_when_nothing_is_imported(self):
        with self.factory() as db:
            with self.assertRaisesRegex(TestParticipantError, "pilot_import"):
                create_test_participant(db)

    def test_refuses_when_a_tier1_variant_is_missing(self):
        with self.factory() as db:
            qa = QAItem(passage_id="t1_judg9", question_text="Q", expected_answer="A")
            db.add(qa)
            db.flush()
            db.add(ExperimentWindow(
                qa_item_id=qa.id, source_passage_id="t1_judg9", content_id="c1",
                window_key="k1", group_index=1, sequence_index=0,
            ))
            db.add(ExperimentPassage(
                source_passage_id="t1_judg9", chapter=1, condition="clean",
                language="zh", passage_text="x",
            ))
            db.flush()
            with self.assertRaisesRegex(TestParticipantError, "variants are missing"):
                create_test_participant(db)

    def test_tier1_plan_leaves_passage_fk_null(self):
        with self.factory() as db:
            qa = QAItem(passage_id="t1_judg9", question_text="Q", expected_answer="A")
            db.add(qa)
            db.flush()
            db.add(ExperimentWindow(
                qa_item_id=qa.id, source_passage_id="t1_judg9", content_id="c1",
                window_key="k1", group_index=1, sequence_index=0,
            ))
            for condition in set(SLOTS):
                db.add(ExperimentPassage(
                    source_passage_id="t1_judg9", chapter=1, condition=condition,
                    language="zh", passage_text=condition,
                ))
            db.flush()
            result = create_test_participant(db)
            cells = db.scalars(select(ExperimentPlanCell).where(
                ExperimentPlanCell.participant_id == result["participant_id"])).all()
            self.assertEqual(len(cells), 8)
            self.assertTrue(all(c.experiment_passage_id is None for c in cells))

    def test_without_plan(self):
        with self.factory() as db:
            result = create_test_participant(db, build_plan=False)
            self.assertIsNone(result["pilot_path"])
            self.assertEqual(result["plan"], [])

    def test_delete_cascades_and_refuses_real_participants(self):
        with self.factory() as db:
            _import_legacy_passages(db)
            result = create_test_participant(db)
            pid = result["participant_id"]
            real = Participant(display_name="real", consented=True)
            qa = QAItem(passage_id="luke1", question_text="Q", expected_answer="A")
            db.add_all([real, qa])
            db.flush()
            assignment = Assignment(participant_id=pid, qa_item_id=qa.id,
                                    status=AssignmentStatus.COMPLETED.value)
            db.add(assignment)
            db.flush()
            db.add(ParticipantResponse(participant_id=pid, qa_item_id=qa.id,
                                       assignment_id=assignment.id, response_text="x"))
            db.commit()

            with self.assertRaisesRegex(TestParticipantError, "Only test participants"):
                delete_test_participant(db, real.id)
            with self.assertRaisesRegex(TestParticipantError, "not found"):
                delete_test_participant(db, "nope")

            removed = delete_test_participant(db, pid)
            db.commit()
            self.assertEqual((removed["assignments"], removed["responses"]), (1, 1))

        with self.factory() as db:
            self.assertIsNone(db.get(Participant, pid))
            for model in (ExperimentPlanCell, Assignment, ParticipantResponse):
                self.assertEqual(db.scalar(select(func.count()).select_from(model).where(
                    model.participant_id == pid)), 0)
            self.assertIsNotNone(db.get(Participant, real.id))
            self.assertIsNotNone(db.get(QAItem, qa.id))

    def test_admin_payloads_expose_is_test(self):
        with self.factory() as db:
            result = create_test_participant(db, build_plan=False)
            db.add(Participant(display_name="real"))
            db.flush()
            rows = {r["display_name"]: r["is_test"] for r in
                    list_participants_dashboard(db)["participants"]}
            self.assertEqual(rows, {result["display_name"]: True, "real": False})
            detail = get_participant_detail(db, result["participant_id"])
            self.assertTrue(detail["participant"]["is_test"])


class TestParticipantExclusionTests(unittest.TestCase):
    """Test participants must never shift real Latin-square blocks or reach exports."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(REPO_ROOT / "human_pilot"))

    def test_plan_builder_all_consented_skips_test_participants(self):
        import build_experiment_plan

        factory = sessionmaker(_engine())
        with factory() as db:
            a = Participant(display_name="a", consented=True)
            t = Participant(display_name="TEST", consented=True,
                            dashboard_preferences={TEST_PARTICIPANT_KEY: True})
            b = Participant(display_name="b", consented=True)
            db.add(a); db.flush(); db.add(t); db.flush(); db.add(b); db.flush()

            class Args:
                participant_ids = None

            got = build_experiment_plan.resolve_participants(db, Args())
            self.assertEqual([p.display_name for p in got], ["a", "b"])

            Args.participant_ids = t.id  # explicit ids still allowed
            self.assertEqual(
                [p.id for p in build_experiment_plan.resolve_participants(db, Args())], [t.id])

    def test_response_export_skips_test_participants_by_default(self):
        import export_pilot_responses

        factory = sessionmaker(_engine())
        with factory() as db:
            qa = QAItem(passage_id="luke1", question_text="Q", expected_answer="A")
            db.add(qa)
            db.flush()
            for name, prefs in (("real", {}), ("TEST", {TEST_PARTICIPANT_KEY: True})):
                p = Participant(display_name=name, consented=True, dashboard_preferences=prefs)
                db.add(p)
                db.flush()
                cell = ExperimentPlanCell(participant_id=p.id, chapter=1, condition="clean",
                                          sequence_index=0, status="done")
                db.add(cell)
                db.flush()
                asg = Assignment(participant_id=p.id, qa_item_id=qa.id,
                                 experiment_cell_id=cell.id,
                                 status=AssignmentStatus.COMPLETED.value)
                db.add(asg)
                db.flush()
                db.add(ParticipantResponse(participant_id=p.id, qa_item_id=qa.id,
                                           assignment_id=asg.id, response_text="x"))
            db.flush()
            self.assertEqual(
                [r["participant_slug"] for r in export_pilot_responses.fetch_records(db, False)],
                ["real"])
            self.assertEqual(len(export_pilot_responses.fetch_records(db, False, True)), 2)


class TestParticipantApiTests(unittest.TestCase):
    def setUp(self):
        self.factory = sessionmaker(_engine(), autoflush=False, expire_on_commit=False)
        app = create_app()
        app.config["TESTING"] = True
        self.client = app.test_client()
        patcher = patch("backend.admin.api.participants.get_session_factory",
                        return_value=self.factory)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _login(self):
        with self.client.session_transaction() as sess:
            sess["admin_role"] = "admin"

    def test_requires_admin(self):
        self.assertEqual(self.client.post("/api/v1/participants/test", json={}).status_code, 401)
        self.assertEqual(self.client.delete("/api/v1/participants/x").status_code, 401)

    def test_create_then_delete(self):
        with self.factory() as db:
            _import_legacy_passages(db)
            db.commit()
        self._login()
        created = self.client.post("/api/v1/participants/test",
                                   json={"display_name": "hard66 check", "language": "zh"})
        self.assertEqual(created.status_code, 201, created.get_json())
        body = created.get_json()
        self.assertEqual(len(body["plan"]), 8)
        pid = body["participant_id"]

        deleted = self.client.delete(f"/api/v1/participants/{pid}")
        self.assertEqual(deleted.status_code, 200, deleted.get_json())
        self.assertEqual(self.client.delete(f"/api/v1/participants/{pid}").status_code, 404)

    def test_failed_plan_rolls_back_the_participant(self):
        self._login()
        response = self.client.post("/api/v1/participants/test", json={})
        self.assertEqual(response.status_code, 400)
        self.assertIn("pilot_import", response.get_json()["message"])
        with self.factory() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(Participant)), 0)


if __name__ == "__main__":
    unittest.main()
