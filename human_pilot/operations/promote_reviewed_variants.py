#!/usr/bin/env python3
"""Promote reviewed pilot texts, refresh LLM inputs, and update existing DB rows.

prepare is offline and stages a reversible release. apply uses a direct database
connection (no application startup migrations), preserves answered assignments,
and archives obsolete model results before changing inputs. No model calls occur.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import zipfile

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO), str(REPO / 'human_pilot'), str(REPO / 'packages/eten-shared')]
import pilot_import as pi
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from eten_shared.models import (Assignment, AnswerReceipt, ExperimentPassage,
    ExperimentPassageVerse, ExperimentPlanCell, ExperimentWindow, Participant,
    ParticipantResponse, PilotQuestionTrial, QAItem)
from eten_shared.experiment_plan import is_test_participant
from eten_shared.domain.assignments import experiment_passage_assignment_kwargs

SOURCES = {
    'grammar30': ('grammar_sol_phrase_test/30%', 'grammar/30%'),
    'mistranslation15': ('mistranslation_sol_length/15%', 'mistranslation/15%'),
    'mistranslation30': ('mistranslation_sol_length/30%', 'mistranslation/30%'),
}
INPUTS = ('passage_target.txt', 'passage_target_decanonicalized.txt',
          'passage_translation.json', 'decanonicalized_metadata.json')
RESULT_PREFIXES = ('generated_answers', 'scores_')

def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()

def sha(path):
    return sha_bytes(path.read_bytes()) if path.is_file() else None

def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')

def snapshot_can_refresh(assignment, *, test_participant, has_response, has_trial):
    if has_response or assignment.completed_at or assignment.status in ('completed', 'skipped'):
        return False
    # Test-only unfinished snapshots may be refreshed. A real participant's
    # presented text remains immutable, including dashboard-only delivery.
    return test_participant or not (
        assignment.delivered_at or assignment.started_at or has_trial
    )

def prepare(root, release_dir):
    if (release_dir / 'manifest.json').exists():
        raise ValueError('Release already exists; use its apply/verify command or a new directory.')
    metadata = pi.load_tier1_metadata(REPO / 'evaluation')
    manifest = {'status': 'prepared', 'root': str(root.resolve()),
                'release_id': release_dir.name, 'cells': [], 'writes': [], 'archive_results': []}
    for passage in metadata:
        pid = passage['id']; base = root / pid
        for condition, (source_rel, canonical_rel) in SOURCES.items():
            source = base / source_rel; canonical = base / canonical_rel
            family = canonical_rel.split('/')[0]
            meta_name = family + '_metadata.json'
            meta = json.loads((source / meta_name).read_text())
            clean = (base / '_base/llm_prompt_high/passage_target.txt').read_text()
            if family == 'mistranslation':
                from evaluation.scripts.variants.current.create_mistranslation_variants import apply_mistranslations
                bank = json.loads((base / '_base/_shared/mistranslation_bank_sol_length_zh.json').read_text())
                expected, _ = apply_mistranslations(clean, rate=meta['files']['passage_target']['requested_rate'], seed=meta['seed'], bank=bank)
                bank_id = bank['bank_id']; actual = meta['files']['passage_target']['actual_rate']
                if meta['bank_id'] != bank_id: raise ValueError(f'Stale mistranslation bank: {pid}')
            else:
                from evaluation.scripts.variants.current.create_grammar_variants import apply_grammar_bank
                inner = meta['files']['passage_target']; bank_id = inner['bank_id']
                bank = json.loads((source.parent / '_grammar_bank' / f'bank_{bank_id}.json').read_text())
                expected, _ = apply_grammar_bank(clean, rate=.3, seed=meta['seed'], bank=bank)
                actual = inner['actual_affected_rate']
                if meta.get('edit_style') != 'llm_structural_v1': raise ValueError(f'Not structural: {pid}')
            if expected != (source / 'passage_target.txt').read_text():
                raise ValueError(f'Reviewed output does not reproduce: {pid}/{source_rel}')
            if (source / 'passage_target.txt').read_bytes() != (source / 'passage_target_decanonicalized.txt').read_bytes():
                raise ValueError(f'Expected matching real-name inputs: {pid}/{source_rel}')
            # Promote text only. QA is already shared by condition and is not
            # replaced from a generation experiment.
            for filename in ('qa_target.json', 'qa_target_decanonicalized.json', 'passage_source_decanonicalized.txt'):
                if (source / filename).read_bytes() != (canonical / filename).read_bytes():
                    raise ValueError(f'QA/source mismatch needs review: {pid}/{filename}')
            text = expected.strip(); verses = pi.parse_tier1_verses(text, passage)
            destinations = [canonical]
            for model_dir in sorted(base.iterdir()):
                # Actual answer-model cells only; generation experiment folders
                # do not contain these standard nested condition directories.
                candidate = model_dir / canonical_rel
                if model_dir.is_dir() and candidate != canonical and (candidate / 'passage_target.txt').is_file():
                    destinations.append(candidate)
            for dest in destinations:
                for filename in (*INPUTS, meta_name):
                    data = (source / filename).read_bytes()
                    if filename == 'decanonicalized_metadata.json':
                        data = data.decode().replace(str(source), str(dest)).encode()
                        data = data.decode().replace(str(source.resolve()), str(dest.resolve())).encode()
                    rel = str((dest / filename).relative_to(root))
                    staged = release_dir / 'staged' / rel
                    staged.parent.mkdir(parents=True, exist_ok=True); staged.write_bytes(data)
                    manifest['writes'].append({'path': rel, 'before': sha(dest / filename), 'after': sha_bytes(data)})
                for f in dest.iterdir():
                    if f.is_file() and f.name.startswith(RESULT_PREFIXES):
                        manifest['archive_results'].append({'path': str(f.relative_to(root)), 'before': sha(f)})
            manifest['cells'].append({'passage': pid, 'condition': condition, 'source': str(source),
                'canonical': canonical_rel, 'bank_id': bank_id, 'actual_coverage': actual,
                'text': text, 'verses': verses, 'model_cells': len(destinations) - 1,
                'source_sha256': sha(source / 'passage_target.txt')})
    if len(manifest['cells']) != 30: raise ValueError('Expected ten passages and three pilot conditions.')
    save(release_dir / 'manifest.json', manifest)
    print(json.dumps({'status': 'prepared', 'pilot_cells': len(manifest['cells']),
        'model_cells': sum(c['model_cells'] for c in manifest['cells']),
        'old_result_files_to_archive': len(manifest['archive_results']),
        'release': str(release_dir)}, indent=2))

def database_update(db, manifest, *, update):
    wanted = {(prefix + c['passage'], c['condition']): c for c in manifest['cells'] for prefix in ('', 'hard66/')}
    query = select(ExperimentPassage).where(
        ExperimentPassage.condition.in_(SOURCES), ExperimentPassage.language == 'zh',
        ExperimentPassage.source_passage_id.in_({k[0] for k in wanted}))
    passages = list(db.scalars(query.with_for_update() if update else query).all())
    if {(p.source_passage_id, p.condition) for p in passages} != set(wanted):
        raise ValueError('The database must contain all 60 regular/Hard66 passage rows; no implicit creation.')
    verses = list(db.scalars(select(ExperimentPassageVerse).where(
        ExperimentPassageVerse.experiment_passage_id.in_([p.id for p in passages]))).all())
    by_passage = {}
    for v in verses: by_passage.setdefault(v.experiment_passage_id, {})[v.verse_number] = v
    backup = {'passages': [], 'verses': [], 'assignments': [], 'trials': []}
    for p in passages:
        cell = wanted[p.source_passage_id, p.condition]; old = by_passage.get(p.id, {})
        if set(old) != {v[0] for v in cell['verses']}:
            raise ValueError(f'Verse labels differ for {p.source_passage_id}/{p.condition}')
        backup['passages'].append({'id': p.id, 'source': p.source_passage_id, 'condition': p.condition, 'passage_text': p.passage_text})
        if update: p.passage_text = cell['text']
        elif p.passage_text != cell['text']: raise ValueError(f'DB passage mismatch: {p.source_passage_id}/{p.condition}')
        for label, value in cell['verses']:
            v = old[label]; backup['verses'].append({'id': v.id, 'text': v.text})
            if update: v.text = value
            elif v.text != value: raise ValueError(f'DB verse mismatch: {p.source_passage_id}/{label}')
    db.flush()
    refreshed = protected = 0
    rows = db.execute(select(Assignment, Participant, QAItem, ExperimentPlanCell)
        .join(Participant, Participant.id == Assignment.participant_id)
        .join(QAItem, QAItem.id == Assignment.qa_item_id)
        .join(ExperimentPlanCell, ExperimentPlanCell.id == Assignment.experiment_cell_id)
        .where(ExperimentPlanCell.condition.in_(SOURCES), QAItem.passage_id.in_({k[0] for k in wanted}))).all()
    pmap = {(p.source_passage_id,p.condition):p for p in passages}
    for assignment, participant, qa, cell in rows:
        trial = db.scalar(select(PilotQuestionTrial).where(PilotQuestionTrial.assignment_id == assignment.id))
        responded = bool(db.scalar(select(AnswerReceipt.id).where(AnswerReceipt.assignment_id == assignment.id))
                         or db.scalar(select(ParticipantResponse.id).where(ParticipantResponse.assignment_id == assignment.id))
                         or (trial and (trial.submitted_at or trial.answer_receipt_id)))
        if not snapshot_can_refresh(assignment, test_participant=is_test_participant(participant), has_response=responded, has_trial=trial is not None):
            protected += 1; continue
        values = experiment_passage_assignment_kwargs(db, pmap[qa.passage_id, cell.condition], qa)
        if not values.get('passage_text'): raise ValueError('Empty replacement assignment snapshot')
        if update and any(getattr(assignment,k) != v for k,v in values.items()):
            backup['assignments'].append({'id': assignment.id, **{k:getattr(assignment,k) for k in values}})
            for k,v in values.items(): setattr(assignment,k,v)
            if trial:
                backup['trials'].append({'id': trial.id, 'metadata': trial.trial_metadata})
                trial.trial_metadata = {**(trial.trial_metadata or {}), 'passage_release': manifest['release_id']}
            refreshed += 1
        elif not update and any(getattr(assignment,k) != v for k,v in values.items()):
            raise ValueError('Unanswered assignment still has stale passage text')
    # Exercise the real delivery helper for every imported question window and
    # changed condition, including both QA sets. No assignments are created.
    windows = db.execute(select(ExperimentWindow, QAItem).join(QAItem, QAItem.id == ExperimentWindow.qa_item_id)
                        .where(ExperimentWindow.source_passage_id.in_({k[0] for k in wanted}))).all()
    checked = 0
    for window, qa in windows:
        for condition in SOURCES:
            p = pmap[qa.passage_id,condition]
            payload = experiment_passage_assignment_kwargs(db,p,qa)
            if not payload.get('passage_text'): raise ValueError('Empty delivery window')
            labels = payload.get('passage_verse_numbers') or []
            expected = ' '.join(dict(wanted[qa.passage_id,condition]['verses'])[label].strip() for label in labels)
            if not labels or payload['passage_text'] != expected: raise ValueError('Delivery does not match released source')
            checked += 1
    db.flush()
    return backup, {'passages':len(passages),'verses':len(verses),'delivery_windows':checked,
                    'refreshed_assignments':refreshed,'preserved_historical_assignments':protected}

def verify_files(root, release_dir, manifest):
    for e in manifest['writes']:
        if sha(root / e['path']) != e['after']: raise ValueError(f'File mismatch: {e["path"]}')
    for e in manifest['archive_results']:
        if (root / e['path']).exists(): raise ValueError(f'Stale result remains: {e["path"]}')

def apply(release_dir):
    manifest = json.loads((release_dir / 'manifest.json').read_text()); root = Path(manifest['root'])
    if manifest['status'] != 'prepared': raise ValueError('This release was already applied.')
    for c in manifest['cells']:
        if sha(Path(c['source'])/'passage_target.txt') != c['source_sha256']: raise ValueError('Reviewed source changed after preparation')
    for e in manifest['writes'] + manifest['archive_results']:
        if sha(root/e['path']) != e['before']: raise ValueError(f'File changed after preparation: {e["path"]}')
    for e in manifest['writes']:
        if sha(release_dir/'staged'/e['path']) != e['after']: raise ValueError('Staged release changed')
    backup_path = release_dir/'previous_files_and_results.zip'
    with zipfile.ZipFile(backup_path,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for e in manifest['writes'] + manifest['archive_results']:
            path=root/e['path']
            if path.exists(): archive.write(path,e['path'])
    url = os.environ.get('DATABASE_URL')
    if not url: raise ValueError('DATABASE_URL is not configured')
    engine=create_engine(url,connect_args={'connect_timeout':10,'options':'-c statement_timeout=30000 -c lock_timeout=10000'})
    applied=[]
    database_committed=False
    try:
        with Session(engine) as db:
            with db.begin():
                backup, stats = database_update(db,manifest,update=True)
                save(release_dir/'previous_database_texts.json',backup)
                for e in manifest['writes']:
                    dest=root/e['path']; dest.parent.mkdir(parents=True,exist_ok=True)
                    temp=dest.with_name(dest.name+'.release-tmp')
                    shutil.copy2(release_dir/'staged'/e['path'],temp);os.replace(temp,dest);applied.append(e)
                for e in manifest['archive_results']:
                    (root/e['path']).unlink();applied.append(e)
                verify_files(root,release_dir,manifest)
                _, validation = database_update(db,manifest,update=False)
        database_committed=True
        with Session(engine) as verification_db:
            _, validation = database_update(verification_db,manifest,update=False)
            verification_db.rollback()
        manifest.update(status='applied',database=stats,verification=validation)
        save(release_dir/'manifest.json',manifest)
        print(json.dumps({'status':'applied','database':stats,'verification':validation,
            'canonical_cells':len(manifest['cells']), 'model_cells':sum(c['model_cells'] for c in manifest['cells']),
            'archived_result_files':len(manifest['archive_results']),'release':str(release_dir)},indent=2))
    except Exception:
        # A reporting failure after commit must not roll back only the files.
        if not database_committed:
            with zipfile.ZipFile(backup_path) as archive:
                for e in applied:
                    dest=root/e['path']
                    if e['before'] is None: dest.unlink(missing_ok=True)
                    else: dest.write_bytes(archive.read(e['path']))
        raise
    finally: engine.dispose()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['prepare','apply'])
    p.add_argument('--root',type=Path,default=REPO/'evaluation/outputs/tier1_bsb_unblinded_5opt_think')
    p.add_argument('--release-dir',type=Path,required=True)
    args=p.parse_args()
    if args.action=='prepare': prepare(args.root,args.release_dir)
    else: apply(args.release_dir)

if __name__=='__main__':main()
