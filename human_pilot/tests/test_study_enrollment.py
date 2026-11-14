"""Admin enrollment, including retries, concurrent allocation and privacy deletions."""
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker

from backend import create_app
from eten_shared.experiment_plan import (
    SLOTS, SOL_SCRATCH_SET, is_test_participant, qa_source_filters, write_participant_plan,
)
from eten_shared.models import Base, ExperimentPlanCell, ExperimentWindow, Participant, PilotRotationCount
from backend.pilot.questionnaire import _screen_out

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pilot_import_reviewed122 as importer


@pytest.fixture
def site(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'pilot.db'}")

    @event.listens_for(engine, "connect")
    def enforce_fks(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, autoflush=False, expire_on_commit=False)
    with factory.begin() as db:
        importer.install(db, importer.load_bank(importer.SOL_SET), qa_set=importer.SOL_SET, apply=True)
    monkeypatch.setattr("backend.admin.api.participants.get_session_factory", lambda: factory)
    monkeypatch.setattr("backend.pilot.routes.get_session_factory", lambda: factory)
    monkeypatch.setenv("ENABLE_EXPERIMENT_ASSIGNMENT", "true")
    monkeypatch.setenv("REQUIRE_QUESTION_AUDIO", "false")
    app = create_app()
    app.config.update(TESTING=True, SECRET_KEY="local-enrollment-test")

    def post(pid, label=""):
        with app.test_client() as client:
            with client.session_transaction() as session:
                session["admin_role"] = "admin"
            response = client.post("/api/v1/participants/study", json={"request_id": pid, "display_name": label})
            return response.status_code, response.get_json()

    yield app, factory, post
    engine.dispose()


def test_two_cohorts_have_exact_per_question_coverage(site):
    app, factory, post = site
    ids = [str(uuid4()) for _ in range(16)]
    # Simultaneous admins, a retry of the same request, and a second batch later.
    with ThreadPoolExecutor(max_workers=5) as pool:
        first = list(pool.map(post, [ids[0], *ids[:8]]))
    assert sorted(code for code, _ in first) == [200] + [201] * 8
    assert {r["rotation"] for _, r in first} == set(range(1, 9))
    assert first[0][1] == first[1][1]
    second = [post(pid) for pid in ids[8:]]
    assert [r["rotation"] for _, r in second] == [1, 3, 5, 7, 2, 4, 6, 8]
    assert [r["enrollment_number"] for _, r in second] == list(range(9, 17))
    with factory() as db:
        for block in (ids[:8], ids[8:]):
            per_item = defaultdict(Counter)
            for qid, condition in db.execute(
                select(ExperimentWindow.qa_item_id, ExperimentPlanCell.condition)
                .join(ExperimentPlanCell, ExperimentPlanCell.chapter == ExperimentWindow.group_index)
                .where(ExperimentPlanCell.participant_id.in_(block), *qa_source_filters(SOL_SCRATCH_SET))
            ):
                per_item[qid][condition] += 1
            assert len(per_item) == 66 and all(counts == Counter(SLOTS) for counts in per_item.values())
        reader = db.get(Participant, ids[0])
        assert not reader.consented and not is_test_participant(reader)
    with app.test_client() as client:
        assert client.post("/api/v1/participants/study", json={"request_id": str(uuid4())}).status_code == 401
        consent = client.get(f"/pilot/api/{ids[0]}/consent")
        assert consent.get_json()["required"]


def test_legacy_screenout_reserves_its_rotation_and_failed_plan_retries(site, monkeypatch):
    _, factory, post = site
    with factory.begin() as db:
        legacy = Participant(target_language="zh")
        db.add(legacy)
        db.flush()
        write_participant_plan(db, legacy, 0, qa_set=SOL_SCRATCH_SET)
        _screen_out(db, legacy)
    pid = str(uuid4())
    with monkeypatch.context() as env:
        env.setenv("REQUIRE_QUESTION_AUDIO", "true")
        status, error = post(pid)
        assert status == 409 and "0 of 66" in error["message"]
    with factory() as db:
        assert db.get(Participant, pid) is None
        assert db.scalar(select(func.sum(PilotRotationCount.issued))) == 1
    assert post("malformed")[0] == 400
    status, reader = post(pid, "Reader B")
    assert (status, reader["rotation"], reader["enrollment_number"], reader["display_name"]) == (201, 2, 2, "Reader B")
    assert post(pid) == (200, reader)
