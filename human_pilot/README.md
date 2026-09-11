# Human pilot scripts

This directory contains the operational lifecycle for the human-participant
experiment. Run commands from the repository root.

```text
pilot_import.py                 import experiment content
build_experiment_plan.py        assign Latin-square condition plans
verify_experiment_delivery.py   verify variant passage resolution
verify_pilot_readiness.py       final study preflight
export_pilot_metrics.py         export timing and accuracy reports
export_pilot_responses.py       export evaluation-compatible responses
reset_experiment_plan.py        deliberate plan reset
pilot_wipe.py                   deliberate pilot-data removal
operations/                     participant and database administration
tests/                          offline regression tests
```

Normal preparation order:

```bash
python human_pilot/pilot_import.py
python human_pilot/build_experiment_plan.py --participant-ids id0,id1
python human_pilot/verify_pilot_readiness.py --participant-ids id0,id1
```

The reset, wipe, purge, migration, and translation-wipe tools can modify or
remove database state. Use their dry-run modes where available.
