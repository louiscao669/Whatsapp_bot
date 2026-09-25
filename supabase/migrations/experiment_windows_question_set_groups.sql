-- Allow a second tier-1 question set in experiment_windows.
-- gold72 uses window groups 1-8; hard66 (human_pilot/pilot_import_hard66.py) uses
-- 101-108 (eten_shared.experiment_plan.QA_SETS). tier1_experiment_windows.sql
-- allowed only 1-8. Also applied automatically at engine start-up
-- (eten_shared.database), only when the live check still lacks the 101-108 range.

alter table public.experiment_windows
    drop constraint if exists experiment_windows_group_index_check;

alter table public.experiment_windows
    add constraint experiment_windows_group_index_check
    check ((group_index between 1 and 8) or (group_index between 101 and 108));
