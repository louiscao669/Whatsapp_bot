"""Finish the from-scratch run before beginning prepared reader inference."""
import fcntl
import time

import run_sol_slide_experiment as run
import report_sol_slide_experiment as report


if __name__ == "__main__":
    # A restarted coordinator can pick up the exact unfinished question.
    with (run.RUN / "reader.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        run.run_readers("scratch", False)
        while not (run.RUN / "grammar_max_coverage.json").exists():
            time.sleep(12)
        run.run_readers("scratch", True)
        with run.db_open() as db:
            expected = len(run.read(run.RUN / "design.json")["bank_questions"]["scratch"]) * 3 * len(run.SHORT)
            while db.execute("SELECT count(*) FROM grades WHERE study='scratch'").fetchone()[0] < expected:
                time.sleep(12)
        report.publish("scratch", True)
        run.run_readers("prepared", False)
        run.run_readers("prepared", True)
