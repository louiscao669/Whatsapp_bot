"""Retry unresolved sentence edits once the first Sol reviewer pass is complete."""
import fcntl
import time

from dotenv import load_dotenv

import run_sol_slide_experiment as run
from evaluation.scripts.variants.current import create_every_sentence_grammar as sentence


if __name__ == "__main__":
    load_dotenv(run.REPO / ".env")
    initial = run.RUN / "grammar_max"
    final = run.RUN / "grammar_max_final"
    with (initial / ".generation.lock").open("r") as lock:
        fcntl.flock(lock, fcntl.LOCK_SH)
        state = run.read(initial / "run_state.json")
        if (set(state["results"]) != set(run.source()[1]) or
                any(p["status"] not in ("complete", "incomplete") for p in state["results"].values())):
            raise RuntimeError("The first grammar pass must finish before the targeted retry.")
    options = ["--source-root", str(run.RAW), "--output-root", str(final), "--resume-from", str(initial),
               "--generator-model","gpt-6.1-sol","--judge-model","gpt-6.1-sol","--seed","2026",
               "--workers","10","--review-workers","4","--candidates","3","--batch-size","4","--retry-rounds","4"]
    sentence.main(options)
    coverage = run.max_verses()
    assert set(coverage) == set(run.source()[1])
    print("Verified maximum-approved sentence variants for",len(coverage),"passages.",flush=True)
