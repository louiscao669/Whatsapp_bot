"""Install the reviewed Chinese MCQs as an isolated test-participant question set."""
import argparse
from collections import defaultdict
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from _bootstrap import use_platform
use_platform()

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session, selectinload
from eten_shared.database import get_database_url, get_session_factory
from eten_shared.mcq_retirement import validate_final_review
from eten_shared.experiment_plan import GROUPS, QA_SETS, SLOTS
from eten_shared.models import (AnswerReceipt, Assignment, ExperimentPassage, ExperimentPassageVerse,
                                ExperimentPlanCell, ExperimentWindow, ParticipantResponse, PilotQuestionTrial,
                                QAItem, utc_now)
from backend.admin.services.participant_assignment_service import skip_participant_assignment
from backend.admin.services.qa_review_service import remove_qa_item_from_review

ROOT = Path(__file__).resolve().parents[1]
BANK = ROOT / "evaluation/datasets/qa/reviewed122"
SET = "reviewed122"
SOL_SET = "reviewed122_sol"
SOL_BANK = BANK.with_name(SOL_SET)
CANNOT_TELL = "根据这段文字无法判断"
SOL_RELEASE = ROOT / "evaluation/datasets/passages/tier1_zh_sol_v1_defect_ladder_2026-11-09"
PREFIX = QA_SETS[SET]["passage_prefix"]


@dataclass(frozen=True)
class Passage:
    reference: str
    text: str
    verses: list[tuple[str, int, str]]
    name: str | None


def checked_json(path, expected_hash):
    data = path.read_bytes()
    if sha256(data).hexdigest() != expected_hash:
        raise ValueError(f"Unexpected release contents in {path.name}")
    return json.loads(data)


SOL_CHOICE_RELEASE = checked_json(SOL_BANK / "choice_release.json",
                                  "f4a936de1afe1c73767bcb0bc4d7e83e4c8ac0835f520dd40c8ca055c2d1994a")
SOL_REVISIONS = SOL_CHOICE_RELEASE["revisions"]
SOL_PREDECESSORS = SOL_CHOICE_RELEASE.get("replacement_predecessors", {})


def slot_order(row):
    return (row["passage_id"], tuple(map(int, next(iter(row["verses"])).split(":"))), row["id"])


def stem_signature(row):
    inputs = [row["id"], row["question"], list(row["verses"].items())]
    return sha256(json.dumps(inputs, ensure_ascii=False).encode()).hexdigest()


def validate_sol_dispositions(dispositions, rows):
    """Check the frozen editorial roster, including manual retirements, and later reviewer decisions."""
    by_id = {r["id"]: r for r in rows}
    baseline = []
    for decision in dispositions:
        cid = decision["id"]
        if "final_mcq_review" in decision:
            finding = decision["final_mcq_review"]
            validate_final_review(by_id[cid], finding)
            if ("grounding_review" in decision or decision.get("status") != "withheld"
                    or decision.get("retired_from_pilot") is not True or finding["verdict"] == "hold"
                    or finding["reason"] != decision.get("reason")):
                raise ValueError(f"Invalid final retirement for {cid}")
            baseline.append({"id": SOL_PREDECESSORS.get(cid, cid), "status": "eligible"})
            continue
        if "grounding_review" not in decision:
            baseline.append(dict(decision, id=SOL_PREDECESSORS.get(cid, cid)))
            continue
        finding = decision["grounding_review"]
        row = by_id[decision["id"]]
        if (decision.get("status") != "withheld" or decision.get("retired_from_pilot") is not True
                or finding.get("verdict") != "retire" or not finding.get("reason")
                or finding["reason"] != decision.get("reason") or not finding.get("model")
                or finding.get("id") != row["id"] or finding.get("requested_fact") != "speech_time"
                or finding.get("timing_evidence") != "dated_content_only" or not finding.get("dated_event")
                or not finding.get("stem_quote") or finding["stem_quote"] not in row["question"]
                or not finding.get("version") or finding.get("stem_signature") != stem_signature(row)
                or not finding.get("quote") or not any(finding["quote"] in v for v in row["verses"].values())):
            raise ValueError(f"Invalid grounding retirement for {row['id']}")
        baseline.append({"id": SOL_PREDECESSORS.get(cid, cid), "status": "eligible"})
    original = (json.dumps(baseline, ensure_ascii=False, indent=2) + "\n").encode()
    if sha256(original).hexdigest() != "769e9ced87d157ceefac2798fddfac82bb2daee4160e1b1256ca90c71052c832":
        raise ValueError("Unexpected changes to the original Sol pilot roster")


def load_bank(qa_set=SET, *, retired_only=False):
    if qa_set == SOL_SET:
        # The Sol release appends the pilot's fixed abstention to the reviewed A–D choices.
        rows = checked_json(SOL_BANK / "zh.json", SOL_CHOICE_RELEASE["zh_sha256"])
        dispositions = json.loads((SOL_BANK / "pilot_review.json").read_text())
        validate_sol_dispositions(dispositions, rows)
    else:
        rows = json.loads((BANK / "zh.json").read_text())
        dispositions = json.loads((BANK / "pilot_review.json").read_text())
    decisions = {r["id"]: r["status"] for r in dispositions}
    if (len(rows) != len(decisions) or len(rows) != len(dispositions) or len(rows) != 122
            or {r["id"] for r in rows} != set(decisions) or set(decisions.values()) - {"eligible", "withheld"}):
        raise ValueError("Incomplete disposition for the 122 source questions")
    retired = {r["id"] for r in dispositions if r.get("retired_from_pilot")}
    if any(decisions[cid] != "withheld" for cid in retired):
        raise ValueError("A retired question cannot also be eligible")
    if retired_only:
        return sorted((r for r in rows if r["id"] in retired), key=slot_order)
    result = [r for r in rows if decisions[r["id"]] == "eligible"]
    if len(result) < len(GROUPS):
        raise ValueError("Too few eligible questions for the pilot plan")
    extra = [CANNOT_TELL] if qa_set == SOL_SET else []
    for r in result:
        choices = r["choices"]
        if (len(set(choices)) != 4 + len(extra) or choices[4:] != extra
                or r["correct"] not in tuple("ABCD")):
            raise ValueError(f"Invalid choices or key for {r['id']}")
    return sorted(result, key=slot_order)


def require_match(obj, fields):
    if any(getattr(obj,k) != v for k,v in fields.items()):
        raise ValueError(f"Existing {type(obj).__name__} {obj.id} differs from this release")


def source_passages(db, source_ids, qa_set):
    if qa_set == SOL_SET:
        manifest = checked_json(SOL_RELEASE / "manifest.json",
                                "f9e6f6132146d954ed17d0f21107794b8b5f6e3072ce09f0e7e2a5f16c4bb241")
        if manifest["release_id"] != SOL_RELEASE.name or set(manifest["files"]) != {f"{p}.json" for p in source_ids}:
            raise ValueError("The QA and Sol release passage IDs differ")
        result = {}
        for pid in sorted(source_ids):
            filename = f"{pid}.json"
            pack = checked_json(SOL_RELEASE / filename, manifest["files"][filename])
            if pack["id"] != pid:
                raise ValueError(f"Wrong passage ID in {filename}")
            for condition in set(SLOTS):
                record = pack["conditions"][condition]
                verses = [(label, i, verse) for i, (label, verse) in enumerate(record["verses"].items())]
                result[pid, condition] = Passage(pack["reference"], record["text"], verses, f"{pid} · {condition}")
        return result
    passages = db.scalars(select(ExperimentPassage).options(selectinload(ExperimentPassage.verses)).where(
        ExperimentPassage.language == "zh", ExperimentPassage.source_passage_id.in_(source_ids),
        ExperimentPassage.condition.in_(set(SLOTS)))).all()
    return {(p.source_passage_id, p.condition): Passage(p.passage_reference, p.passage_text,
            [(v.verse_number, v.position, v.text) for v in p.verses], p.name) for p in passages}


def install(db, rows, *, apply=False, qa_set=SET):
    if qa_set not in (SET, SOL_SET):
        raise ValueError(f"Unsupported question bank {qa_set}")
    if apply and db.get_bind().dialect.name == "postgresql":
        db.execute(select(func.pg_advisory_xact_lock(742908122)))
    config = QA_SETS[qa_set]
    offset = config["group_offset"]
    retired = load_bank(qa_set, retired_only=True) if qa_set == SOL_SET else []
    retired_ids = {r["id"] for r in retired}
    if any(r["id"] in retired_ids for r in rows):
        raise ValueError("Cannot import a retired question as eligible")
    # Preserve the original sequence and group boundaries across retirements.
    layout = sorted([*rows, *retired], key=slot_order) if retired else rows
    original = source_passages(db, {r["passage_id"] for r in layout}, qa_set)
    aliases = sorted({(r["source"],r["passage_id"]) for r in layout})
    def alias(source, pid):
        return f"{config['passage_prefix']}{source}/{pid}"
    bank_sources = [alias(s,p) for s,p in aliases]
    existing_passages = db.scalars(select(ExperimentPassage).options(selectinload(ExperimentPassage.verses))
        .where(ExperimentPassage.source_passage_id.in_(bank_sources))).all()
    saved = {(p.source_passage_id,p.condition):p for p in existing_passages}
    for index,(source,pid) in enumerate(aliases):
        for condition in sorted(set(SLOTS)):
            passage = original.get((pid,condition))
            if not passage or not passage.verses:
                raise ValueError(f"No Chinese passage verses for {pid} / {condition}")
            source_id = alias(source,pid)
            fields = dict(source_passage_id=source_id,chapter=offset+1+index,condition=condition,
                          language="zh",passage_reference=passage.reference,passage_text=passage.text)
            verses = passage.verses
            if old := saved.get((source_id,condition)):
                require_match(old,fields)
                if verses != [(v.verse_number,v.position,v.text) for v in old.verses]:
                    raise ValueError(f"Passage verse mismatch: {source_id} / {condition}")
            elif apply:
                clone = ExperimentPassage(**fields,name=f"{qa_set} · {passage.name or condition}")
                clone.verses = [ExperimentPassageVerse(verse_number=n,position=i,text=t) for n,i,t in verses]
                db.add(clone)

    existing_items = {q.id:q for q in db.scalars(select(QAItem).where(QAItem.passage_id.in_(bank_sources)))}
    existing_windows = {w.qa_item_id:w for w in db.scalars(select(ExperimentWindow).where(
        ExperimentWindow.group_index.between(offset+1,offset+len(GROUPS))))}
    expected_ids = set()
    historical_ids = set()
    replacements = {}
    groups = defaultdict(int)
    retired_item_ids = [q.id for q in existing_items.values() if q.form_group_id in retired_ids]
    if apply and retired_item_ids:
        retiring_groups = {w.group_index for w in existing_windows.values() if w.content_id in retired_ids}
        lock_retiring_participants(db, retiring_groups, retired_item_ids)
    for index,r in enumerate(layout):
        pid = r["passage_id"]
        source_id = alias(r["source"],pid)
        key = r["correct"]
        identity = f"eten:{qa_set}:{r['source']}:{r['id']}"
        revisions = SOL_REVISIONS.get(r["id"], ()) if qa_set == SOL_SET else ()
        identities = [identity] + [f"{identity}:{version}" for version in revisions]
        prior_ids = {}
        qid = str(uuid5(NAMESPACE_URL, identities[-1]))
        for value in identities[:-1]:
            prior_ids[str(uuid5(NAMESPACE_URL, value))] = r["id"]
        predecessor = SOL_PREDECESSORS.get(r["id"]) if qa_set == SOL_SET else None
        if predecessor:
            prior_identity = f"eten:{qa_set}:{r['source']}:{predecessor}"
            for value in [prior_identity, *(f"{prior_identity}:{v}" for v in SOL_REVISIONS.get(predecessor, ()))]:
                prior_ids[str(uuid5(NAMESPACE_URL, value))] = predecessor
        historical_ids.update(prior_ids)
        prior_windows = [existing_windows[value] for value in prior_ids if value in existing_windows]
        if len(prior_windows) + (qid in existing_windows) > 1:
            raise ValueError(f"Multiple delivery windows for {r['id']}")
        expected_ids.add(qid)
        clean = {n:t for n,_,t in original[pid,"clean"].verses}
        labels = list(r["verses"])
        if not labels or any(n not in clean for n in labels):
            raise ValueError(f"Missing clean verse in the reviewed window of {r['id']}")
        if any(clean[n] != r["verses"][n] for n in labels):
            raise ValueError(f"Live clean passage differs from the reviewed window of {r['id']}")
        qfields = dict(passage_id=source_id,passage_reference=r["reference"],question_text=r["question"],
                       question_type="mcq",expected_answer=r["choices"]["ABCD".index(key)],
                       mcq_choices=r["choices"],mcq_correct_choice=key,form_group_id=r["id"],automatic_form="mcq",
                       active=False)
        group = offset+1+(index*len(GROUPS)//len(layout))
        wfields = dict(qa_item_id=qid,source_passage_id=source_id,content_id=r["id"],group_index=group,
                       sequence_index=100*offset+index,window_key="|".join(labels),verse_numbers=labels,
                       window_ordinals=[list(clean).index(n) for n in labels])
        if r["id"] in retired_ids:
            for version_id in [*prior_ids, qid]:
                content_id = prior_ids.get(version_id, r["id"])
                if old_item := existing_items.get(version_id):
                    require_match(old_item, dict(form_group_id=content_id, passage_id=source_id))
                    if apply:
                        remove_qa_item_from_review(old_item)
                if old_window := existing_windows.get(version_id):
                    require_match(old_window, dict(wfields, qa_item_id=version_id, content_id=content_id))
                    if apply:
                        db.delete(old_window)
            continue
        groups[group]+=1
        if (qid in existing_items and qa_set == SOL_SET and r["choices"][4:] == [CANNOT_TELL]
                and existing_items[qid].mcq_choices == r["choices"][:4]):
            require_match(existing_items[qid], dict(qfields, mcq_choices=r["choices"][:4]))
            if apply:
                existing_items[qid].mcq_choices = r["choices"]
        elif qid in existing_items:
            require_match(existing_items[qid],qfields)
        elif apply:
            db.add(QAItem(id=qid,**qfields))
        if prior_windows:
            # Move the delivery window while preserving every previously assigned revision.
            window = prior_windows[0]
            require_match(window, dict(wfields, qa_item_id=window.qa_item_id, content_id=prior_ids[window.qa_item_id]))
            if apply:
                db.flush()
                window.qa_item_id = qid
                window.content_id = r["id"]
                replacements.update({old_id: qid for old_id in prior_ids})
        elif qid in existing_windows:
            require_match(existing_windows[qid],wfields)
        elif apply:
            db.add(ExperimentWindow(**wfields))
    if (set(existing_items) | set(existing_windows)) - expected_ids - historical_ids:
        raise ValueError("This namespace already contains a different release")
    if apply:
        db.flush()
        if replacements:
            preserve_in_progress_revisions(db, replacements, existing_windows)
        if retired_item_ids:
            skip_unanswered_retired(db, retired_item_ids)
    return dict(qa_set=qa_set, questions=len(rows), existing=len(existing_windows),
                passages=len(aliases)*len(set(SLOTS)),groups=dict(groups))


def preserve_in_progress_revisions(db, replacements, windows):
    """Switch unseen queued items and exclude second exposures in still-open cells.

    Deployed selectors de-duplicate by QA item ID. A skipped assignment on the
    new revision records that the participant already got this source question.
    It has no presentation, trial or answer. Finished cells never reopen.
    """
    groups = {windows[qid].group_index for qid in replacements if qid in windows}
    lock_retiring_participants(db, groups, replacements.keys())
    prior = (select(Assignment).join(ExperimentPlanCell, ExperimentPlanCell.id == Assignment.experiment_cell_id)
             .where(Assignment.qa_item_id.in_(replacements), ExperimentPlanCell.status.in_(("pending", "active"))))
    unseen = prior.where(Assignment.status == "assigned", Assignment.started_at.is_(None),
                         Assignment.delivered_at.is_(None))
    for model in (PilotQuestionTrial, AnswerReceipt, ParticipantResponse):
        unseen = unseen.where(~select(model.id).where(model.assignment_id == Assignment.id).exists())
    if db.get_bind().dialect.name == "postgresql" and db.scalars(unseen.limit(1)).first() is not None:
        # GET /question can present a pre-minted item without taking the mint
        # lock. Drain in-flight readers before swapping a never-presented item.
        # Fail immediately on contention; the entire release is safe to retry.
        db.execute(text("LOCK TABLE assignments IN ACCESS EXCLUSIVE MODE NOWAIT"))
    queued_ids = {a.id for a in db.scalars(unseen)}
    seen = defaultdict(list)
    for old in db.scalars(prior):
        seen[old.participant_id, replacements[old.qa_item_id]].append(old)
    already_assigned = set(db.execute(select(Assignment.participant_id, Assignment.qa_item_id)
                                      .where(Assignment.qa_item_id.in_(set(replacements.values())))).tuples())
    for (pid, new_id), previous in seen.items():
        if (pid, new_id) in already_assigned:
            continue
        if len(previous) == 1 and previous[0].id in queued_ids:
            previous[0].qa_item_id = new_id
        else:
            db.add(Assignment(participant_id=pid, qa_item_id=new_id, experiment_cell_id=previous[0].experiment_cell_id,
                              status="skipped", completed_at=utc_now()))
    db.flush()


def lock_retiring_participants(db, groups, item_ids):
    if db.get_bind().dialect.name != "postgresql":
        return
    participants = select(ExperimentPlanCell.participant_id).where(
        ExperimentPlanCell.chapter.in_(groups), ExperimentPlanCell.status.in_(("pending", "active")))
    pending = select(Assignment.participant_id).where(Assignment.qa_item_id.in_(item_ids),
                                                    Assignment.status.in_(("assigned", "in_progress")))
    for pid in db.scalars(participants.union(pending).order_by("participant_id")):
        db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:pid))"), {"pid": pid})


def skip_unanswered_retired(db, item_ids):
    """Keep recorded answers intact, including submissions still being scored."""
    open_assignments = select(Assignment).where(
        Assignment.qa_item_id.in_(item_ids), Assignment.status.in_(("assigned", "in_progress")))
    unanswered = open_assignments.where(
        ~select(AnswerReceipt.id).where(AnswerReceipt.assignment_id == Assignment.id).exists(),
        ~select(ParticipantResponse.id).where(ParticipantResponse.assignment_id == Assignment.id).exists())
    for assignment in db.scalars(unanswered.order_by(Assignment.id).with_for_update()).all():
        skip_participant_assignment(db, assignment.participant_id, assignment.id, notify_successor=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qa-set", choices=(SET, SOL_SET), default=SET,
                        help="reviewed122_sol uses the frozen natural-name Sol passages.")
    parser.add_argument("--apply",action="store_true",help="Commit the new bank; the default only checks it.")
    args=parser.parse_args()
    rows = load_bank(args.qa_set)
    if args.apply:
        with get_session_factory().begin() as db:
            print(json.dumps(install(db, rows, apply=True, qa_set=args.qa_set)))
    else:
        # A dry run must also skip the application's automatic startup migrations.
        with Session(create_engine(get_database_url())) as db:
            if db.get_bind().dialect.name == "postgresql":
                db.execute(text("SET TRANSACTION READ ONLY"))
            print(json.dumps(install(db, rows, qa_set=args.qa_set)))
    print("Installed." if args.apply else "Content preview verified. Use --apply to run startup migrations and install.")


if __name__ == "__main__":
    main()
