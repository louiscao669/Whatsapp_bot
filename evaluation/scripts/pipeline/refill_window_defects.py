"""Run fresh grammar and mistranslation writers and reviewers on held Sol windows."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from dotenv import load_dotenv

from evaluation.scripts.pipeline.build_prepared_window_conditions import ROOT, SOL_RELEASE, grammar, read, save
from evaluation.scripts.variants.banks.mistranslation_validation import validate_reviewed_bank


def window_input(verses, family):
    if family == 'grammar':
        return '\n'.join(f'{label.split(":")[-1]} {body}' for label, body in verses.items())
    return '\n'.join(verses.values())


def bank_dir(root, w, family):
    return root / w['passage_id'] / w['verses'][0].replace(':', '-') / family


def jobs(draft):
    for w in draft['windows']:
        for family in ('grammar', 'mistranslation'):
            if any(key.startswith(family) and c['status'] == 'held' for key, c in w['conditions'].items()):
                yield w, family


def generate(w, family, root, *, max_candidates=60, batch_size=12, max_batches=5, target_rate=.60):
    directory = bank_dir(root, w, family)
    directory.mkdir(parents=True, exist_ok=True)
    text = window_input(w['conditions']['clean']['verses'], family)
    dest = directory / 'window_bank.json'
    if dest.exists():
        bank = read(dest)
        if family == 'grammar':
            grammar.validate_grammar_bank(text, bank)
        else:
            validate_reviewed_bank(bank, text)
            if bank.get('schema_version') != 3:
                raise ValueError('This output contains a legacy mistranslation bank; choose a new output root for anchored bundles.')
            expected=dict(max_candidates=max_candidates,batch_size=batch_size,max_batches=max_batches,target_rate=target_rate,
                          span_policy='minimal_edges_v1',combination_policy='retain_quoted_fluency_failures_v1')
            if any(bank['configuration'].get(k)!=v for k,v in expected.items()):
                raise ValueError('Cached generation bounds differ; choose a new output root (response caches can be copied).')
        return len(bank.get('entries', bank.get('candidates', bank.get('replacements', []))))
    if family == 'grammar':
        passage = read(SOL_RELEASE / (w['passage_id'] + '.json'))
        writer = 'gpt-6-astra' if w['passage_id'] == 't1_acts20' else 'gpt-6.1-sol'
        judge = 'gpt-6.1-sol'
        bank = grammar.build_grammar_bank(text, bank_dir=directory,
            seed=passage['families']['grammar']['seed'], max_rate=.50, max_candidates=3,
            proposal_cache=grammar.GrammarProposalCache(directory/'proposals.json', model=writer),
            cache=grammar.GrammarJudgmentCache(directory/'judgments.json', model=judge),
            meaning_cache=grammar.GrammarMeaningCache(directory, model=judge),
            retry_rounds=1, review_workers=3)
    else:
        from evaluation.scripts.variants.banks.mistranslation_bundles import build_bank
        bank = build_bank(passage=text, chapter=w['reference'],cache_dir=directory,
                          max_candidates=max_candidates,batch_size=batch_size,max_batches=max_batches,target_rate=target_rate)
    save(dest, bank)
    return len(bank.get('entries', bank.get('candidates', bank.get('replacements', []))))


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--draft', required=True, type=Path)
    cli.add_argument('--root', required=True, type=Path)
    cli.add_argument('--workers', type=int, default=4, choices=range(1, 9))
    scope=cli.add_mutually_exclusive_group(required=True)
    scope.add_argument('--passage-id',help='One Bible passage while developing the workflow')
    scope.add_argument('--all-passages',action='store_true',help='Use only after the full run is authorized')
    cli.add_argument('--window-start',help='Optional exact first verse, e.g. 13:6')
    cli.add_argument('--expand-mistranslation',action='store_true',help='Build higher coverage even for already in-band windows')
    cli.add_argument('--families',nargs='+',choices=('grammar','mistranslation'),default=['grammar','mistranslation'])
    cli.add_argument('--max-candidates',type=int,default=60)
    cli.add_argument('--batch-size',type=int,default=12)
    cli.add_argument('--max-batches',type=int,default=5)
    cli.add_argument('--mistranslation-target',type=float,default=.60)
    args = cli.parse_args()
    load_dotenv(ROOT/'.env')
    failures = []
    completed = []
    draft=read(args.draft)
    scoped=[w for w in draft['windows'] if (args.all_passages or w['passage_id']==args.passage_id)
            and (not args.window_start or w['verses'][0]==args.window_start)]
    if not scoped:cli.error('No windows match the requested passage/window')
    if args.window_start and args.all_passages:cli.error('--window-start requires one --passage-id')
    work=list(jobs(dict(windows=scoped)))
    if args.expand_mistranslation:
        work.extend((w,'mistranslation') for w in scoped if not any(old['id']==w['id'] and f=='mistranslation' for old,f in work))
    work=[(w,f) for w,f in work if f in args.families]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(generate, w, family, args.root,max_candidates=args.max_candidates,
                               batch_size=args.batch_size,max_batches=args.max_batches,target_rate=args.mistranslation_target): (w, family)
                   for w, family in work}
        for future in as_completed(futures):
            w, family = futures[future]
            row = dict(id=w['id'], reference=w['reference'], family=family)
            try:
                row['approved'] = future.result()
                completed.append(row)
            except Exception as exc:
                row['error'] = f'{type(exc).__name__}: {exc}'
                failures.append(row)
            print(f'{len(completed)+len(failures)}/{len(futures)} {row}', flush=True)
            save(args.root/'generation.json', dict(completed=completed, failures=failures))
    if failures:
        raise SystemExit(f'{len(failures)} window generation jobs need a retry')


if __name__ == '__main__':
    main()
