from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import json
import os
import re
import subprocess
import sys
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
GENERATOR = Path("/Users/louiscao/bible translation/ETEN-Bible-translation-project/v3/combo")
SCRIPTS = REPO / "evaluation/scripts/mcq/diagnostics"
MANIFEST = json.loads((ROOT / "manifest.json").read_text())


def check_technical_failures(directory):
    failed = []
    for path in (directory / "window_checkpoints").glob("v*.json"):
        if path.stem.endswith("_drafts"):
            continue
        if re.search(r'connection error|timed out|request timeout|error code: (?:429|5\d\d)|"status": "unchecked"|server disconnected', path.read_text(), re.I):
            failed.append(path)
    return failed


def run_unit(unit):
    directory = Path(unit["run"])
    for stage, name in [("generation", "run_checkpointed_chapter"), ("curation", "curate_generated_chapter")]:
        args = [sys.executable, "-u", str(SCRIPTS / (name + ".py")), "--generator-root", str(GENERATOR), "--run-dir", str(directory)]
        for attempt in range(1, 4):
            with (directory / (stage + ".log")).open("a") as log:
                result = subprocess.run(args, stdout=log, stderr=subprocess.STDOUT)
            failures = check_technical_failures(directory) if stage == "generation" else []
            if result.returncode == 0 and not failures:
                break
            print(unit["unit"], stage, "attempt",attempt,"incomplete", [p.stem for p in failures],flush=True)
            if attempt == 3:
                raise RuntimeError(f"{unit['unit']} {stage} needs recovery")
            if failures:
                archive = directory / "interrupted_windows"
                archive.mkdir(exist_ok=True)
                for path in failures:
                    path.rename(archive / (path.stem + "_" + str(__import__("time").time_ns()) + ".json"))
        print(unit["unit"], stage, "complete",flush=True)
    return unit["unit"]


if __name__ == "__main__":
    if not os.environ.get("OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = dotenv_values(REPO / ".env")["OPENAI_API_KEY"]
    os.environ["OPENAI_BASE_URL"]="https://api.openai.com/v1"
    os.environ["LANGCHAIN_TRACING_V2"]="false"
    os.environ["LANGSMITH_TRACING"]="false"
    errors = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run_unit, unit) for unit in MANIFEST if not unit["carried"]]
        for job in as_completed(futures):
            try:
                job.result()
            except Exception as exc:
                print(exc,flush=True)
                errors.append(str(exc))
    if errors:
        raise SystemExit("\n".join(errors))

