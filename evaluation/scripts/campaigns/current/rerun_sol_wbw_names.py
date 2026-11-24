"""Replay the corrected Google WBW windows in a separate copy of the latest slides experiment."""
import argparse
import fcntl
from hashlib import sha256
import sqlite3

import requests

import run_sol_slide_experiment as run
import map_sol_slide_choices as mapper
import score_sol_slide_open as grader

ORIGINAL = run.RUN
PARENT = ORIGINAL.with_name('sol_uzziah_enemies_stem_2026-11-13')
PREPARED_KEYS = ORIGINAL.with_name('sol_judges9_curse_stem_2026-11-13')
FOLDER = ORIGINAL.with_name('sol_wbw_name_rerun_2026-11-13')
REPORT = run.REPORT.with_name(FOLDER.name)
run.RUN = FOLDER
run.REPORT = REPORT
EXPECTED = {'scratch': 49, 'prepared': 37}


def prior_db():
    return sqlite3.connect((PARENT / 'observations.sqlite').as_uri() + '?mode=ro', uri=True)


def excerpts(row, old, new):
    pid = row['passage_id']
    return tuple(' '.join(verses[v] for v in row['verses']) for verses in
                 (old[pid]['conditions']['wbw']['verses'], new[pid]['verses']))


def protocol():
    design = run.read(PARENT / 'design.json')
    rows = run.read(PARENT / 'sol_questions.json')
    assert rows == run.pilot.load_bank(run.pilot.SOL_SET) and run.digest(rows) == design['bank_sha']
    assert design['inference'] == run.CONFIG and design['open_scoring_model'] == run.JUDGE
    for path, digest in design['source_files'].items():
        assert sha256((run.REPO / path).read_bytes()).hexdigest() == digest
    old = {pid: run.read(run.pilot.SOL_RELEASE / f'{pid}.json') for pid in design['passages']}
    assert all(run.digest(old[pid]) == digest for pid, digest in design['passages'].items())
    new = run.pilot.sol_wbw_release(old)
    assert all(new[pid]['parent_text_sha256'] == pack['conditions']['wbw']['text_sha256']
               and new[pid]['text_sha256'] == sha256(new[pid]['text'].encode()).hexdigest() for pid, pack in old.items())
    selected = {study: [r for r in rows if r['source'] == source and len(set(excerpts(r, old, new))) == 2]
                for study, source in run.STUDIES.items()}
    assert {s: len(rr) for s, rr in selected.items()} == EXPECTED
    return rows, design, old, new, selected


def initialize():
    rows, design, old, new, selected = protocol()
    manifest = {'baseline': PARENT.name, 'baseline_bank': design['bank_sha'],
                'corrected_release_sha256': run.pilot.SOL_WBW_SHA256, 'models': design['models'],
                'inference': design['inference'], 'scorer': run.JUDGE, 'condition': 'wbw',
                'affected_ids': {s: [r['id'] for r in rr] for s, rr in selected.items()}}
    manifest_file = FOLDER / 'revision.json'
    if manifest_file.exists():
        if run.read(manifest_file) != manifest:
            raise ValueError('Inputs differ from the existing rerun.')
    else:
        run.save(manifest_file, manifest)
    # The grading helpers load the QA snapshot. Passage inputs are supplied separately below.
    run.save(FOLDER / 'sol_questions.json', rows)
    for study, directory in [('scratch', PARENT), ('prepared', PREPARED_KEYS)]:
        keys = run.read(directory / f'{study}_english_grading_keys.json')
        expected = [(r['id'], r['question'], r['choices']['ABCD'.index(r['correct'])])
                    for r in rows if r['source'] == run.STUDIES[study]]
        assert run.digest(expected) == keys['signature']
        run.save(FOLDER / f'{study}_english_grading_keys.json', keys)

    target = FOLDER / 'observations.sqlite'
    if not target.exists():
        tmp = FOLDER / 'initial.sqlite'
        with prior_db() as prior, sqlite3.connect(tmp) as db:
            prior.backup(db)
            for study, group in selected.items():
                for row in group:
                    params = (study, row['id'])
                    for table in ('mapped_observations', 'grades', 'observations'):
                        result = db.execute(f"DELETE FROM {table} WHERE condition='wbw' AND study=? AND item=?", params)
                        if table == 'observations':
                            assert result.rowcount == 10
        prior.close()
        db.close()
        tmp.replace(target)
    print('Verified paired questions, original prompts will be checked against their saved hashes.', flush=True)


def read_study(study):
    _, design, old, new, groups = protocol()
    session = requests.Session()
    response = session.get(run.LOCAL + '/api/tags', timeout=20)
    response.raise_for_status()
    local = {m['name']: m['digest'] for m in response.json()['models']}
    assert all(local.get(m) == h for m, h in design['models'].items())
    with prior_db() as prior, run.db_open() as db:
        if study == 'prepared':
            scratch_n = len(design['bank_questions']['scratch'])
            expected = (7 * scratch_n, 3 * scratch_n)
            completed = (db.execute("select count(*) from observations where study='scratch' and condition='wbw' and form='mcq'").fetchone()[0],
                         db.execute("select count(*) from grades where study='scratch' and condition='wbw'").fetchone()[0])
            if completed != expected:
                raise ValueError('Complete scratch reading and grading before starting prepared.')
        for index, (model, thinking) in enumerate(run.MODELS):
            name = run.model_name(model, thinking)
            mode = False if study == 'prepared' and index < 2 else thinking
            for form in (('mcq', 'open') if index < 3 else ('mcq',)):
                for row in groups[study]:
                    before, after = excerpts(row, old, new)
                    old_body, _ = run.request_for(row, before, model, mode, form, index >= 4)
                    body, public = run.request_for(row, after, model, mode, form, index >= 4)
                    key = (study, name, 'wbw', form, row['id'])
                    query = 'select request_hash from observations where (study,model,condition,form,item)=(?,?,?,?,?)'
                    old_hash = run.digest([study, local[model], old_body])
                    new_hash = run.digest([study, local[model], body])
                    assert prior.execute(query, key).fetchone() == (old_hash,) and new_hash != old_hash
                    done = db.execute(query, key).fetchone()
                    if done:
                        assert done == (new_hash,)
                        continue
                    saved = db.execute('select answer from answers where hash=?', (new_hash,)).fetchone()
                    with db:
                        if saved:
                            answer = saved[0]
                        else:
                            answer, tokens, reason = run.infer(session, body)
                            db.execute('insert into answers values(?,?,?,?)', (new_hash, answer, tokens, reason))
                        choice = outcome = None
                        if form == 'mcq':
                            choice = (run.small.parse_choice(answer, public['choices'])[0] if index >= 4 else
                                      run.gen.selected_choice_from_raw_answer(public, answer) if answer else None)
                            outcome = ('correct' if choice == row['correct'] else 'abstain' if choice == 'E' else
                                       'incorrect' if choice else 'invalid')
                        db.execute('insert into observations values(?,?,?,?,?,?,?,?)', (*key, new_hash, choice, outcome))
                print(study, name, form, len(groups[study]), 'complete', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=['initialize', 'read', 'score'])
    parser.add_argument('study', nargs='?', choices=run.STUDIES)
    args = parser.parse_args()
    if args.stage != 'initialize' and not args.study:
        parser.error('Supply the QA set.')
    FOLDER.mkdir(parents=True, exist_ok=True)
    lock_name = f'{args.study}-scoring.lock' if args.stage == 'score' else 'run.lock'
    with (FOLDER / lock_name).open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.stage == 'initialize':
            initialize()
        elif args.stage == 'read':
            read_study(args.study)
        else:
            rows, _, _, _, _ = protocol()
            size = sum(r['source'] == run.STUDIES[args.study] for r in rows)
            mapper.map_choices(args.study)
            grader.grade(args.study)
            with run.db_open() as db:
                assert db.execute("select count(*) from grades where study=? and condition='wbw'",
                                  (args.study,)).fetchone()[0] == size * 3


if __name__ == '__main__':
    main()
