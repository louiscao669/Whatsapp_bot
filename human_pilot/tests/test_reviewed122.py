from pathlib import Path
import json
import sys

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pilot_import_reviewed122 as importer
from backend.admin.services.test_participants_service import create_test_participant, test_participant_options as options
from eten_shared.domain.assignments import experiment_passage_assignment_kwargs, resolve_experiment_passage
from eten_shared.experiment_plan import SLOTS, participant_qa_set
from eten_shared.models import Base, ExperimentPassage, ExperimentPassageVerse, ExperimentPlanCell, Participant, QAItem
from eten_shared.question_discovery import select_next_experiment_cell_item, select_next_qa_item


def test_real_scratch_planner_continues_across_enrollment_batches(monkeypatch):
    from collections import Counter
    from sqlalchemy.orm import sessionmaker
    import build_experiment_plan as planner
    from eten_shared.experiment_plan import SOL_SCRATCH_SET, qa_set_groups

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine)
    monkeypatch.setattr(planner, "get_session_factory", lambda url: factory)
    ids = [f"study-{i}" for i in range(16)]
    with factory.begin() as db:
        importer.install(db, importer.load_bank(importer.SOL_SET), qa_set=importer.SOL_SET, apply=True)
        db.add_all(Participant(id=pid, target_language="zh") for pid in ids)
        create_test_participant(db, qa_set=SOL_SCRATCH_SET)

    def enroll(selected, *args):
        monkeypatch.setattr(sys, "argv", ["build_experiment_plan", "--database-url", "sqlite://",
                                          "--participant-ids", ",".join(selected), *args])
        planner.main()

    enroll(ids, "--dry-run")
    with factory() as db:
        assert not planner.scratch_rotation_counts(db)
        assert not db.get(Participant, ids[0]).dashboard_preferences
    enroll(ids[:5])
    enroll(ids[4:12])  # An already planned reader is skipped on retry.
    for size in (12, 16):
        if size == 16:
            enroll(ids[12:])
        with factory() as db:
            assert all(participant_qa_set(db, pid) == SOL_SCRATCH_SET for pid in ids[:size])
            cells = db.scalars(select(ExperimentPlanCell).where(ExperimentPlanCell.participant_id.in_(ids))).all()
            assert len(cells) == 8 * size
            for group in qa_set_groups(SOL_SCRATCH_SET):
                counts = Counter(cell.condition for cell in cells if cell.chapter == group)
                assert counts.pop("clean") == size // 4
                assert set(counts) == set(SLOTS) - {"clean"}
                assert set(counts.values()) == ({1, 2} if size == 12 else {2})


def test_reviewed_bank_reaches_only_its_test_plan():
    rows = importer.load_bank()
    original = json.loads((importer.BANK / "zh.json").read_text())
    verses = {}
    for r in original:
        verses.setdefault(r["passage_id"], {}).update(r["verses"])
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        for chapter,(pid,texts) in enumerate(verses.items(),1):
            for condition in set(SLOTS):
                p = ExperimentPassage(source_passage_id=pid,language="zh",condition=condition,chapter=chapter,
                                      passage_text=" ".join(texts.values()))
                p.verses = [ExperimentPassageVerse(verse_number=n,position=i,text=texts[n])
                            for i,n in enumerate(sorted(texts,key=lambda s:tuple(map(int,s.split(":")))))]
                db.add(p)
        db.flush()
        assert importer.install(db, rows, apply=True)["existing"] == 0
        assert importer.install(db, rows, apply=True)["existing"] == len(rows)
        assert next(bank["windows"] for bank in options(db)["qa_sets"] if bank["key"] == importer.SET) == len(rows)
        participant = db.get(Participant, create_test_participant(db,qa_set=importer.SET)["participant_id"])
        assert select_next_qa_item(db,participant) is None
        q,cell = select_next_experiment_cell_item(db,participant)
        assert q and q.passage_id.startswith(importer.PREFIX)
        assert resolve_experiment_passage(db,cell,q,"zh").condition == cell.condition
        clean_cell = ExperimentPlanCell(condition="clean")
        items = db.scalars(select(QAItem)).all()
        assert len(items)==len(rows)
        by_id = {r["id"]:r for r in rows}
        for item in items:
            source = by_id[item.form_group_id]
            assert item.mcq_correct_choice == source["correct"] and item.mcq_choices == source["choices"]
            clean = resolve_experiment_passage(db,clean_cell,item,"zh")
            delivered = experiment_passage_assignment_kwargs(db,clean,item)
            assert delivered["passage_text"] == " ".join(source["verses"].values())
            assert delivered["passage_verse_numbers"] == list(source["verses"])


def test_defect_panel_compares_omitted_and_padded_verses_against_the_delivered_snapshot():
    from types import SimpleNamespace
    from backend.pilot.service import _test_excerpt_changes

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        for condition, verses in [
            ("clean", [("1:1", "甲"), ("1:2", "乙"), ("1:3", "丙丁"), ("1:4", "戊")]),
            ("omission30", [("1:2", "乙"), ("1:3", "丙"), ("1:4", "己")]),
        ]:
            p = ExperimentPassage(source_passage_id="sample", language="zh", chapter=1,
                                  condition=condition, passage_text=" ".join(v for _, v in verses))
            p.verses = [ExperimentPassageVerse(verse_number=n, position=i, text=v)
                        for i, (n, v) in enumerate(verses)]
            db.add(p)
        db.flush()
        participant = SimpleNamespace(target_language="zh")
        assignment = SimpleNamespace(passage_text="乙 丙", passage_verse_numbers=["1:2", "1:3"])
        trial = SimpleNamespace(condition="omission30", trial_metadata={"passage_id": "sample", "window_key": "1:1|1:2"})
        assert _test_excerpt_changes(db, participant, assignment, trial) == [
            {"verse": "1:1", "clean": "甲", "shown": ""},
            {"verse": "1:3", "clean": "丙丁", "shown": "丙"},
        ]
        assignment.passage_text = "different saved wording"
        assert _test_excerpt_changes(db, participant, assignment, trial) is None


def test_sol_revision_moves_existing_windows_and_preserves_delivered_wording(monkeypatch):
    from eten_shared.models import Assignment, ExperimentWindow

    rows = importer.load_bank(importer.SOL_SET)
    old_by_id = {r["id"]: r for r in importer.load_bank()}
    old_rows = []
    for row in rows:
        cid = importer.SOL_PREDECESSORS.get(row["id"], row["id"])
        old_rows.append(dict(row, id=cid, question=old_by_id[cid]["question"], choices=old_by_id[cid]["choices"]))
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        with monkeypatch.context() as patch:
            patch.setattr(importer, "SOL_REVISIONS", {})
            importer.install(db, old_rows, qa_set=importer.SOL_SET, apply=True)
        windows = {w.content_id: (w.id, w.qa_item_id) for w in db.scalars(select(ExperimentWindow))}
        cid = "t1_1kgs13:cj4m"
        person = Participant()
        db.add(person)
        db.flush()
        assignment = Assignment(participant_id=person.id, qa_item_id=windows[cid][1])
        db.add(assignment)
        db.flush()
        importer.install(db, rows, qa_set=importer.SOL_SET)
        assert db.get(ExperimentWindow, windows[cid][0]).qa_item_id == assignment.qa_item_id
        assert all(len(q.mcq_choices) == 4 for q in db.scalars(select(QAItem)))
        david = "t1_2sam21:kjsg"
        v2_rows = [dict(r, choices=list(r["choices"])) for r in rows]
        previous_c = old_by_id[david]["choices"][2]
        next(r for r in v2_rows if r["id"] == david)["choices"][2] = previous_c
        with monkeypatch.context() as patch:
            patch.setitem(importer.SOL_REVISIONS, david, ("v2",))
            importer.install(db, v2_rows, qa_set=importer.SOL_SET, apply=True)
        david_v2 = db.get(ExperimentWindow, windows[david][0]).qa_item_id
        assert david_v2 != windows[david][1]
        for _ in range(2):
            importer.install(db, rows, qa_set=importer.SOL_SET, apply=True)
        active = {w.content_id: (w.id, w.qa_item_id) for w in db.scalars(select(ExperimentWindow))}
        assert len(active) == len(windows) == len(rows)
        prior = {k: windows[importer.SOL_PREDECESSORS.get(k, k)] for k in active}
        assert {k for k in active if prior[k] != active[k]} == (
            set(importer.SOL_REVISIONS).intersection(active) | set(importer.SOL_PREDECESSORS))
        assert all(active[k][0] == prior[k][0] for k in active)
        for new_id, old_id in importer.SOL_PREDECESSORS.items():
            assert new_id in active and old_id not in active
            assert db.get(QAItem, windows[old_id][1]).form_group_id == old_id
            assert db.get(QAItem, active[new_id][1]).form_group_id == new_id
        assert active[david][1] != david_v2
        assert db.get(QAItem, david_v2).mcq_choices[2] == previous_c
        for row in rows:
            item = db.get(QAItem, active[row["id"]][1])
            assert (item.question_text, item.mcq_choices) == (row["question"], row["choices"])
        assert assignment.qa_item.question_text == old_by_id[cid]["question"]
        assert assignment.qa_item.mcq_choices == old_by_id[cid]["choices"]


def test_revision_refreshes_unseen_queue_and_excludes_repeat_presentations():
    from eten_shared.models import Assignment, ExperimentWindow, utc_now

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db, db.begin():
        old, revised = [QAItem(passage_id="sol", question_text=s, expected_answer="A") for s in ("old", "new")]
        db.add_all([old, revised])
        db.flush()
        window = ExperimentWindow(qa_item_id=old.id, source_passage_id="sol", content_id="q",
                                  group_index=301, window_key="9:4", sequence_index=1)
        db.add(window)
        work = []
        for cell_status, was_seen in [("active", True), ("active", False), ("done", True)]:
            person = Participant()
            db.add(person)
            db.flush()
            cell = ExperimentPlanCell(participant_id=person.id, chapter=301, condition="clean",
                                      status=cell_status, sequence_index=0)
            db.add(cell)
            db.flush()
            a = Assignment(participant_id=person.id, qa_item_id=old.id, experiment_cell_id=cell.id,
                           delivered_at=utc_now() if was_seen else None)
            db.add(a)
            work.append(a)
        db.flush()
        for _ in range(2):
            importer.preserve_in_progress_revisions(db, {old.id: revised.id}, {old.id: window})
        shown, queued, done = work
        assert shown.qa_item_id == done.qa_item_id == old.id
        assert queued.qa_item_id == revised.id and queued.status == "assigned"
        exclusions = db.scalars(select(Assignment).where(Assignment.status == "skipped")).all()
        assert [(a.participant_id, a.qa_item_id, a.delivered_at) for a in exclusions] == [
            (shown.participant_id, revised.id, None)
        ]


def test_retiring_items_preserves_other_windows_and_assignment_history(monkeypatch):
    from eten_shared.models import Assignment, ExperimentWindow

    key = importer.SOL_SET
    eligible = importer.load_bank(key)
    retired = importer.load_bank(key, retired_only=True)
    ids = {r["id"] for r in retired}
    assert "t1_2kgs11:uo39" in ids
    old_rows = sorted([*eligible, *retired], key=importer.slot_order)
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        with monkeypatch.context() as patch:
            patch.setattr(importer, "load_bank", lambda *args, retired_only=False: [] if retired_only else eligible)
            importer.install(db, old_rows, qa_set=key, apply=True)
        def windows():
            return {w.content_id: (w.id, w.qa_item_id, w.group_index, w.sequence_index)
                    for w in db.scalars(select(ExperimentWindow))}
        old = windows()
        qa_id = old[retired[0]["id"]][1]
        participant = Participant()
        next_reader = Participant()
        db.add_all([participant, next_reader])
        db.flush()
        saved = Assignment(participant_id=participant.id, qa_item_id=qa_id, status="completed")
        pending = Assignment(participant_id=next_reader.id, qa_item_id=qa_id, status="assigned")
        db.add_all([saved, pending])
        db.flush()
        importer.install(db, eligible, qa_set=key)
        assert windows() == old and db.get(QAItem, qa_id).review_removed_at is None
        for _ in range(2):
            importer.install(db, eligible, qa_set=key, apply=True)
            assert windows() == {k: v for k, v in old.items() if k not in ids}
        assert pending.status == "skipped"
        assert saved.status == "completed" and saved.qa_item.mcq_choices == retired[0]["choices"]
        assert saved.qa_item.review_removed_at is not None


@pytest.mark.parametrize(("plan_key", "source", "regular"), [
    ("reviewed122_sol", None, False),
    ("reviewed122_sol_prepared", "Prepared60", False),
    ("reviewed122_sol_scratch", "Hard77", False),
    ("reviewed122_sol_scratch", "Hard77", True),
])
def test_sol_bank_binds_all_windows_and_serves_the_participant(monkeypatch, plan_key, source, regular):
    from uuid import uuid4
    from sqlalchemy.orm import sessionmaker
    from backend import create_app
    from eten_shared.experiment_plan import ExperimentPlanError, write_participant_plan
    from eten_shared.models import AnswerReceipt, Assignment, ExperimentWindow

    key = importer.SOL_SET
    rows = importer.load_bank(key)
    eligible_ids = {r["id"] for r in json.loads((importer.SOL_BANK / "pilot_review.json").read_text())
                    if r["status"] == "eligible"}
    assert {r["id"] for r in rows} == eligible_ids
    count = sum(source is None or row["source"] == source for row in rows)
    by_id = {r["id"]: r for r in rows}
    packs = {p.stem: json.loads(p.read_text()) for p in importer.SOL_RELEASE.glob("t1_*.json")}
    windows = {w["id"]: w for w in json.loads(importer.SOL_WINDOWS.read_text())["windows"]}
    for pid, release in importer.sol_wbw_release(packs).items():
        packs[pid]["conditions"]["wbw"] = release
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, autoflush=False, expire_on_commit=False)
    with factory.begin() as db:
        assert importer.install(db, rows, qa_set=key)["existing"] == 0
        assert db.scalar(select(QAItem)) is None
        result = importer.install(db, rows, apply=True, qa_set=key)
        assert (result["questions"], result["passages"]) == (len(eligible_ids), 140)
        assert importer.install(db, rows, apply=True, qa_set=key)["existing"] == len(eligible_ids)
        for item in db.scalars(select(QAItem)):
            r = by_id[item.form_group_id]
            assert item.mcq_correct_choice == r["correct"] and item.mcq_choices == r["choices"]
            assert not item.active
            for condition in set(SLOTS):
                passage_variant = packs[r["passage_id"]]["conditions"][condition]
                p = resolve_experiment_passage(db, ExperimentPlanCell(condition=condition), item, "zh")
                if r["source"] == "Hard77" and condition in importer.window_release.DOSES:
                    passage_variant = windows[r["id"]]["conditions"][condition]
                else:
                    assert p.passage_text == passage_variant["text"]
                snapshot = experiment_passage_assignment_kwargs(db, p, item)
                labels = snapshot["passage_verse_numbers"]
                assert labels and snapshot["passage_text"] == " ".join(passage_variant["verses"][n] for n in labels)
                expected = [n for n in r["verses"] if n in passage_variant["verses"]]
                assert labels == expected
                if condition not in ("omission15", "omission30"):
                    assert labels == list(r["verses"])

    monkeypatch.setattr("backend.admin.api.participants.get_session_factory", lambda: factory)
    monkeypatch.setattr("backend.pilot.routes.get_session_factory", lambda: factory)
    legacy_queue = []

    def run_background(job, *args, key=None, **kwargs):
        with factory.begin() as db:
            if regular and not legacy_queue and key and key[0] == "premint":
                # An in-progress link may already have a same-group successor
                # queued by the previous release. Preserve it for a later turn.
                with monkeypatch.context() as old:
                    old.setattr("backend.pilot.service.select_next_participant_qa_item",
                                lambda db, participant, **kw: select_next_experiment_cell_item(db, participant))
                    legacy_queue.append(job(db, *args, **kwargs).id)
                return
            job(db, *args, **kwargs)

    monkeypatch.setattr("backend.pilot.routes.run_in_background", run_background)
    monkeypatch.setenv("PILOT_QUESTIONNAIRE_ENABLED", "1")
    monkeypatch.setenv("ENABLE_EXPERIMENT_ASSIGNMENT", "true")
    monkeypatch.setenv("REQUIRE_QUESTION_AUDIO", "false")
    app = create_app()
    app.config["TESTING"] = True
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["admin_role"] = "admin"
    opts = client.get("/api/v1/participants/test/options").get_json()["qa_sets"]
    assert next(option["windows"] for option in opts if option["key"] == plan_key) == count
    if regular:
        with factory.begin() as db:
            participant = Participant(target_language="zh", consented=False)
            db.add(participant)
            db.flush()
            for preview in (importer.SET, key, key + "_prepared"):
                with pytest.raises(ExperimentPlanError, match="test participants only"):
                    write_participant_plan(db, participant, 0, qa_set=preview)
            write_participant_plan(db, participant, 0, qa_set=plan_key)
            assert select_next_qa_item(db, participant) is None
            pid = participant.id
    else:
        created = client.post("/api/v1/participants/test", json={"qa_set": plan_key, "language": "zh"})
        assert created.status_code == 201, created.get_json()
        pid = created.get_json()["participant_id"]
    expected = {r["id"] for r in rows if source is None or r["source"] == source}
    assert len(expected) == count
    with factory() as db:
        assert participant_qa_set(db, pid) == plan_key
        plan = {cell.chapter: cell.condition for cell in db.scalars(
            select(ExperimentPlanCell).where(ExperimentPlanCell.participant_id == pid)
        )}
    prefix = "/pilot/api/" + pid
    assert client.post(prefix + "/consent", json={"agreed": True}).status_code == 200
    for section, data in [
        ("eligibility", {"answers": {"a1_age_18_plus": "yes", "a2_first_language": "mandarin",
                                     "a3_reading_comfort": "comfortable"}}),
        ("background", {"answers": {"b1_age_band": "25_34"}}),
        ("religion", {"answers": {}, "religion_consent": False}),
    ]:
        response = client.post(prefix + "/questionnaire", json={"section": section, **data})
        assert response.status_code == 200, response.get_json()
    answered = set()
    assignment_ids = []
    conditions = set()
    previous_family = None
    for _ in range(count):
        response = client.get(prefix + "/question")
        assert response.status_code == 200, response.get_json()
        question = response.get_json()["question"]
        assert question is not None
        assignment_id = question["assignment_id"]
        assignment_ids.append(assignment_id)
        if not answered:
            assert client.get(prefix + "/question").get_json()["question"]["assignment_id"] == assignment_id
        with factory() as db:
            assignment = db.get(Assignment, assignment_id)
            item = db.get(QAItem, question["qa_item_id"])
            assert item.passage_id.startswith("reviewed122_sol/")
            row = by_id[item.form_group_id]
            assert row["id"] not in answered
            answered.add(row["id"])
            cell = db.get(ExperimentPlanCell, assignment.experiment_cell_id)
            window = db.scalar(select(ExperimentWindow).where(ExperimentWindow.qa_item_id == item.id))
            condition = cell.condition
            assert cell.chapter == window.group_index and condition == plan[window.group_index]
            family = condition.rstrip("0123456789")
            assert family != previous_family
            previous_family = family
            conditions.add(condition)
            verses = (windows[row["id"]]["conditions"][condition]["verses"] if row["source"] == "Hard77"
                      else packs[row["passage_id"]]["conditions"][condition]["verses"])
            if regular:
                assert not {"test_info", "condition", "defect_type", "defect_rate", "correct_choice",
                            "correct_answer", "verse_changes", "manually_written_fields"} & question.keys()
            else:
                info = question["test_info"]
                assert info["condition"] == condition
                if condition == "clean":
                    assert "verse_changes" not in info
                else:
                    clean = packs[row["passage_id"]]["conditions"]["clean"]["verses"]
                    labels = set(assignment.passage_verse_numbers)
                    if condition.startswith("omission"):
                        labels.update(row["verses"])
                    assert info["verse_changes"] == [
                        {"verse": n, "clean": original, "shown": verses.get(n, "")}
                        for n, original in clean.items() if n in labels and original != verses.get(n, "")
                    ]
            assert question["passage_text"] == " ".join(verses[v] for v in assignment.passage_verse_numbers)
            assert question["question"] == row["question"]
            assert [c["text"] for c in question["choices"]] == row["choices"]
            assert question["choices"][-1] == {"letter": "E", "text": "无法判断"}
        assert client.post(prefix + "/question/viewed", json={"assignment_id": assignment_id}).status_code == 200
        answer = client.post(prefix + "/answers", json={"assignment_id": assignment_id,
                             "submission_id": str(uuid4()), "answer": "E" if len(answered) == 1 else row["correct"],
                             "active_time_ms": 1000})
        assert answer.status_code == 200, answer.get_json()
    assert answered == expected and conditions == set(SLOTS)
    if regular:
        assert len(legacy_queue) == 1 and legacy_queue[0] in assignment_ids[2:]
    assert client.get(prefix + "/question").get_json()["state"] == "complete"
    with factory() as db:
        receipts = db.scalars(select(AnswerReceipt)).all()
        assert len(receipts) == count and sum(r.raw_answer == "E" for r in receipts) == 1


def test_sol_wbw_upgrade_preserves_delivered_and_refreshes_queued_windows():
    from eten_shared.models import Assignment, ExperimentWindow, utc_now

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    rows = importer.load_bank(importer.SOL_SET)
    previous = json.loads((importer.SOL_RELEASE / "t1_judg9.json").read_text())["conditions"]["wbw"]
    with Session(engine) as db:
        importer.install(db, rows, qa_set=importer.SOL_SET, apply=True)
        source = "reviewed122_sol/Hard77/t1_judg9"
        passage = db.scalar(select(ExperimentPassage).where(ExperimentPassage.source_passage_id == source,
                                                            ExperimentPassage.condition == "wbw"))
        passage.passage_text = previous["text"]
        for verse in passage.verses:
            verse.text = previous["verses"][verse.verse_number]
        window = next(w for w in db.scalars(select(ExperimentWindow).where(ExperimentWindow.source_passage_id == source))
                      if "9:30" in w.verse_numbers)
        before = " ".join(previous["verses"][n] for n in window.verse_numbers)
        assignments = []
        for delivered in (False, True):
            reader = Participant()
            db.add(reader)
            db.flush()
            cell = ExperimentPlanCell(participant_id=reader.id, chapter=window.group_index, condition="wbw",
                                      sequence_index=0, status="active")
            db.add(cell)
            db.flush()
            item = Assignment(participant_id=reader.id, experiment_cell_id=cell.id, qa_item_id=window.qa_item_id,
                              passage_text=before, passage_verse_numbers=window.verse_numbers,
                              delivered_at=utc_now() if delivered else None)
            db.add(item)
            assignments.append(item)
        db.flush()
        importer.install(db, rows, qa_set=importer.SOL_SET)
        assert [a.passage_text for a in assignments] == [before, before]
        for _ in range(2):
            importer.install(db, rows, qa_set=importer.SOL_SET, apply=True)
        updated = experiment_passage_assignment_kwargs(db, passage, assignments[0].qa_item)
        assert assignments[0].passage_text == updated["passage_text"]
        assert "西布勒" in updated["passage_text"] and "耶比底" not in updated["passage_text"]
        assert assignments[1].passage_text == before and "西布勒" not in before


def test_window_release_restores_omitted_verse_only_for_unseen_assignments(monkeypatch):
    from eten_shared.models import Assignment, ExperimentWindow, utc_now

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    rows = importer.load_bank(importer.SOL_SET)
    manifest = json.loads(importer.SOL_WINDOWS.read_text())
    record = next(w for w in manifest["windows"] if w["id"] == "2chr_26_1-23/v6-8:1")
    prefix = "reviewed122_sol/Hard77/"
    layout = sorted([*rows, *importer.load_bank(importer.SOL_SET, retired_only=True)], key=importer.slot_order)
    with Session(engine) as db:
        with monkeypatch.context() as parent:
            parent.setattr(importer.window_release, "validate_release", lambda *args: {})
            importer.install(db, rows, qa_set=importer.SOL_SET, apply=True)
        window = db.scalar(select(ExperimentWindow).where(ExperimentWindow.content_id == record["id"]))
        qa = db.get(QAItem, window.qa_item_id)
        passage = resolve_experiment_passage(db, ExperimentPlanCell(condition="omission15"), qa, "zh")
        previous = experiment_passage_assignment_kwargs(db, passage, qa)
        assert previous["passage_verse_numbers"] == ["26:6", "26:8"]
        with pytest.raises(ValueError, match="Installed window differs"):
            importer.window_release.verify_installed(db, manifest, rows, prefix, layout)
        assignments = []
        for delivered in (False, True):
            reader = Participant()
            db.add(reader)
            db.flush()
            cell = ExperimentPlanCell(participant_id=reader.id, chapter=window.group_index, condition="omission15",
                                      sequence_index=0, status="active")
            db.add(cell)
            db.flush()
            a = Assignment(participant_id=reader.id, experiment_cell_id=cell.id, qa_item_id=qa.id,
                           delivered_at=utc_now() if delivered else None, **previous)
            db.add(a)
            assignments.append(a)
        db.flush()
        importer.install(db, rows, qa_set=importer.SOL_SET)
        assert assignments[0].passage_verse_numbers == previous["passage_verse_numbers"]
        for _ in range(2):
            importer.install(db, rows, qa_set=importer.SOL_SET, apply=True)
        fresh, seen = assignments
        assert fresh.passage_verse_numbers == record["verses"]
        assert fresh.passage_text == " ".join(record["conditions"]["omission15"]["verses"].values())
        assert seen.passage_text == previous["passage_text"]
        assert seen.passage_verse_numbers == previous["passage_verse_numbers"]
        report = importer.window_release.verify_installed(db, manifest, rows, prefix, layout)
        assert report["verified_question_presentations"] == 528
