"""Build versioned study passage conditions from the finalized Sol clean texts."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import random
import shutil
import subprocess
import sys

from dotenv import load_dotenv

from evaluation.scripts.pipeline.compare_clean_passages import BASE, ROOT, RUN, freeze, read, save
from evaluation.scripts.variants.current import create_grammar_variants as grammar
from evaluation.scripts.variants.current import create_mistranslation_variants as mis
from evaluation.scripts.variants.current import create_omission_variants as omission
from evaluation.scripts.variants.banks.mistranslation_validation import validate_reviewed_bank
from evaluation.scripts.variants.banks.extend_mistranslation_coverage import extend_bank

FILES = ("passage_target.txt", "passage_target_decanonicalized.txt")
RATES = (.15, .30)


def hash_file(path):
    return sha256(path.read_bytes()).hexdigest()


def dose_plan(weights, total):
    bank = {"entries": [{"content_chars": w} for w in weights], "total_content_chars": total, "max_rate": .3}
    return grammar.plan_nested_selections(bank, RATES, tolerance_pp=2)


def build_grammar(run, pid):
    root = run / "release"
    # The short Acts 20 passage required a second proposer to reach the study dose.
    use_supplement = pid == "t1_acts20"
    proposer = "gpt-6-astra" if use_supplement else "gpt-6.1-sol"
    candidate_limit = 6 if use_supplement else 3
    rounds = 3 if use_supplement else 8
    command = [sys.executable, "-u", "-m", "evaluation.scripts.variants.current.create_grammar_variants",
               "--root", str(root), "--source-model-dir", "_base", "--passage-dirs", pid,
               "--rates", "30%", "--output-model-dir", "grammar", "--generator-model", proposer,
               "--judge-model", "gpt-6.1-sol", "--proposal-batch-size", "8", "--max-candidates-per-clause", str(candidate_limit),
               "--retry-rounds", str(rounds), "--coverage-tolerance-pp", "2", "--seed", "2026", "--review-workers", "6"]
    command_file = "grammar_supplement_command.json" if use_supplement else "grammar_parallel_command.json"
    freeze(run/pid/command_file, command)
    with (run/pid/"grammar.log").open("a") as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True, cwd=ROOT)
    print("Grammar verified and rendered:", pid, flush=True)


def build_base_conditions(run, pid):
    directory = run / "release" / pid
    base = directory / "_base/llm_prompt_high"
    text = (base / FILES[0]).read_text()
    assert text == (base / FILES[1]).read_text()
    assert sha256(text.strip().encode()).hexdigest() == read(run/pid/"clean_release.json")["sha256"]
    omission.create_clean_copy(base, directory / "omission", force=False)
    seed = read(BASE/pid/"omission/15%/omission_metadata.json")["seed"]
    units = omission.passage_units(text)
    candidates = [i for i,u in enumerate(units) if u["omittable"] and u["content_chars"]]
    random.Random(seed).shuffle(candidates)
    weights = [units[i]["content_chars"] for i in candidates]
    plan = dose_plan(weights, sum(weights))
    for rate in RATES:
        omission.create_variant(source_method_dir=base,output_dir=directory/"omission",rate=rate,seed=seed,force=True,
                                selections={f: [candidates[i] for i in plan[rate]] for f in FILES})
    wbw = BASE / pid / "google_word_by_word"
    old = read(wbw/"passage_translation.json")
    if old["method"] != "google_word_by_word" or old["source_texts"] != read(base/"passage_translation.json")["source_texts"]:
        raise ValueError(f"Word-by-word English source mismatch: {pid}")
    if (wbw/FILES[0]).read_text() != (wbw/FILES[1]).read_text():
        raise ValueError(f"Conflicting word-by-word texts: {pid}")
    dest = directory / "google_word_by_word"
    dest.mkdir(exist_ok=True)
    for file in (*FILES,"passage_source_decanonicalized.txt"):
        shutil.copy2(wbw/file,dest/file)
    # The legacy JSON predates the participant-facing whitespace normalization.
    # Build this release's JSON from the actual verified serving text.
    served_text = (dest/FILES[0]).read_text().strip()
    save(dest/"passage_translation.json", dict(old, translations=[served_text],
         original_translation_json_sha256=hash_file(wbw/"passage_translation.json")))
    freeze(run/pid/"wbw_provenance.json", {"method": old["method"], "identical_english": True,
           "original": str(wbw.relative_to(ROOT)), "sha256": hash_file(dest/FILES[0])})


def build_mistranslations(run, pid):
    directory = run / "release" / pid
    base = directory / "_base/llm_prompt_high"
    text = (base / FILES[0]).read_text()
    shared = base.parent / "_shared"
    bank = read(shared/"mistranslation_bank_sol_length_zh.json")
    validate_reviewed_bank(bank, text)
    exclusions = [item for p in BASE.glob("t1_*/_base/_shared/mistranslation_bank_sol_length_zh.json")
                  for item in read(p).get("curation",{}).get("excluded_pairs",[])]
    bank = extend_bank(passage=text,parent=bank,cache_dir=directory/"_coverage_cache",
                       output=shared/"mistranslation_bank_coverage_zh.json",exclusions=exclusions,workers=4)
    excluded_pairs = {(e["source"],e["target"]) for e in exclusions}
    groups = mis.candidate_groups(mis.find_occurrences(text,mis.normalized_replacements(bank)))
    usable = [i for i,g in enumerate(groups) if (g["source"],g["target"]) not in excluded_pairs]
    plan = dose_plan([groups[i]["changed_chars"] for i in usable],mis.content_len(text))
    seed = read(BASE/pid/"mistranslation/15%/mistranslation_metadata.json")["seed"]
    for rate in RATES:
        mis.create_variant(source_method_dir=base, output_dir=directory/"mistranslation", rate=rate, seed=seed,
                           force=True, bank=bank, selections={f: [usable[i] for i in plan[rate]] for f in FILES})
    print("Mistranslation doses verified and rendered:",pid,flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=["grammar","base","mistranslation"])
    parser.add_argument("--passages",nargs="+")
    parser.add_argument("--workers",type=int,default=3)
    args=parser.parse_args()
    load_dotenv(ROOT/".env")
    all_pids = sorted(p.name for p in BASE.glob("t1_*/") if (p/"_base/llm_prompt_high").is_dir())
    pids = args.passages or all_pids
    assert len(all_pids)==10 and set(pids)<=set(all_pids)
    action={"grammar":build_grammar, "base":build_base_conditions, "mistranslation":build_mistranslations}[args.action]
    if not 1 <= args.workers <= 10:
        raise ValueError("Choose 1–10 independent passage workers")
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(lambda pid:action(RUN,pid),pids))


if __name__ == "__main__":
    main()
