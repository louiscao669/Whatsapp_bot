# Deploy only the VM runtime

`vm-files.txt` is the authoritative allowlist for `deploy-vm.sh`. Each non-comment
line is a repository-relative Python glob; `**` is recursive. Files outside the
allowlist are never staged or uploaded. This replaces full-repository `git pull`
for future VM application updates. Git itself does not read this allowlist.

Included:

- Platform backend for admin, expert review, participant pilot and gamified dashboard.
- Compiled admin/expert React frontend; static pilot/dashboard frontends and consent text.
- Messaging backend, including WhatsApp and Telegram.
- Shared models, storage, scoring and live question assignment in
  `packages/eten-shared/eten_shared/question_discovery` and its shared dependencies.
- Service configuration and runtime requirement files.
- Luke 1–8 passage/all-format QA source files; Tier-1 original and BSB passages;
  Tier-1 easy QAs, canonical Gold-72 five-option QAs, and canonical Strong-66 QAs.
- The Tier-1 passage catalog, Gold-72 item/window files, pilot partition, and
  original/canonical QA verse-window maps.

`QA_algorithm/scripts` is offline research and is not imported by the running
services. Its inputs, outputs, simulations and model-fitting code are excluded,
as are unlisted experimental datasets, research reports, participant CSV files, tests, Git
history, node_modules, Python environments and caches. If a future runtime path
needs a research module, add only that module and its dependencies to the allowlist.
Secrets, uploads, recordings, logs and database files are independently denied.
The passage catalog is the only allowed CSV; participant CSVs remain blocked.
Dataset patterns match the current JSON/TXT files only, excluding backup copies
and alternative Gold-72 distractor experiments. Running services read QAs and
passages from the database. Transferring these source files does not import them
or update database content. The full pilot import also depends on translated
condition outputs and analysis inputs; this payload is not a standalone pilot
rebuild bundle, and does not transfer those evaluation outputs.
Symlinks and paths outside the repository are refused.

## Usage from your Mac

Requires Python 3.10+, Node/npm and installed admin build dependencies locally,
plus SSH access and rsync on both machines. Install frontend dependencies with
`npm ci` in `platform/frontends/admin` if needed. Every invocation rebuilds the
admin/expert frontend and stops if the build or required-file checks fail.

```bash
# Local payload inspection; no VM connection or upload.
sh deploy/deploy-vm.sh --list

# Preview the exact remote transfer. HOST is your SSH alias or user@hostname.
sh deploy/deploy-vm.sh --host HOST

# Upload only the runtime payload after reviewing the preview.
sh deploy/deploy-vm.sh --host HOST --apply
```

The destination defaults to `/opt/eten-whatsapp-bot`; change it with
`--remote-dir /absolute/application/path`. The directory must already exist and
be writable by the SSH user. SSH options, identity files and ports belong in your
local SSH configuration. The script does not infer a VM or copy credentials.

Uploads update the existing application in place, not as an atomic release.
Use a maintenance window when changing incompatible backend files. Copying files
does not install service units, change the database, install dependencies or
restart any process. When requirements change, install them in the VM's existing
virtual environment, then restart the affected services using your established
operational procedure. New servers still need `.env`, a virtual environment and
service installation as described in `vm-migration/README.md` and `systemd/`.

There is deliberately no remote deletion. VM `.env`, `.venv`, uploads and runtime
data stay untouched. Old research directories, obsolete code and old frontend
assets already on the VM remain until separately audited and cleaned up. This
allowlist prevents new unnecessary transfers; it does not reclaim existing disk
space. Avoid subsequent full Git pulls, which would reintroduce excluded files.

There is no automatic VM-to-local pull of runtime data. Retrieve study data and
backups separately through the appropriate export/backup process.
