-- Match the Gold72, Hard66, reviewed Chinese, and versioned Sol test banks.

alter table public.experiment_windows
    drop constraint if exists experiment_windows_group_index_check,
    add constraint experiment_windows_group_index_check
    check ((group_index between 1 and 8) or (group_index between 101 and 108)
           or (group_index between 201 and 208) or (group_index between 301 and 308));
