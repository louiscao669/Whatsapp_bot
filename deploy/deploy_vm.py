#!/usr/bin/env python3
"""Build and preview an allowlisted runtime transfer; --apply enables the upload."""
from __future__ import annotations

import argparse
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
DENIED_PARTS = {'.git', '.aws', '.ssh', '.venv', 'venv', 'node_modules', '__pycache__',
                '.pytest_cache', 'tests', 'test', 'uploads', 'recordings', 'logs',
                'outputs', 'output'}
DENIED_SUFFIXES = {'.pyc', '.pyo', '.log', '.csv', '.sqlite', '.sqlite3', '.db', '.pem', '.key', '.map'}
REQUIRED = ('config.py', 'platform/wsgi.py', 'platform/requirements.txt',
            'platform/backend/__init__.py', 'platform/frontends/admin/dist/index.html',
            'platform/frontends/pilot/index.html', 'platform/frontends/user_dashboard/index.html',
            'message-bot/app.py', 'message-bot/requirements.txt',
            'packages/eten-shared/pyproject.toml',
            'packages/eten-shared/eten_shared/question_discovery/selection.py',
            'packages/eten-shared/eten_shared/question_discovery/experiment_selection.py',
            'deploy/gunicorn/gunicorn.conf.py')


# The passage catalog is the sole deployable CSV; participant exports stay blocked.
DATA_CSV = 'evaluation/datasets/obscure_narrative_passages_tier1.csv'


def forbidden(relative: Path) -> bool:
    return (bool(set(relative.parts) & DENIED_PARTS)
            or any(part.startswith('.env') for part in relative.parts)
            or relative.name == '.DS_Store'
            or (relative.suffix in DENIED_SUFFIXES and relative.as_posix() != DATA_CSV)
            or relative.name.endswith(('~', '.bak', '.orig', '.tmp', '.prestemfix'))
            or '.bak_' in relative.name)


def select_files(root: Path, manifest: Path) -> list[Path]:
    selected = set()
    for line in manifest.read_text().splitlines():
        pattern = line.strip()
        if not pattern or pattern.startswith('#'):
            continue
        if PurePosixPath(pattern).is_absolute() or '..' in PurePosixPath(pattern).parts or '\\' in pattern:
            raise ValueError(f'Unsafe allowlist pattern: {pattern}')
        matches = 0
        for path in root.glob(pattern):
            relative = path.relative_to(root)
            if forbidden(relative):
                continue
            # Neither a link nor any linked parent may redirect a deployment read.
            if any((root / Path(*relative.parts[:i])).is_symlink()
                   for i in range(1, len(relative.parts) + 1)):
                raise ValueError(f'Symlinks are not deployable: {relative}')
            if path.is_file():
                if root.resolve() not in path.resolve().parents:
                    raise ValueError(f'Path escapes repository: {relative}')
                selected.add(relative)
                matches += 1
        if not matches:
            raise ValueError(f'Allowlist pattern selected no files: {pattern}')
    missing = [name for name in REQUIRED if Path(name) not in selected]
    if missing:
        raise ValueError(f'Missing runtime files: {", ".join(missing)}')
    return sorted(selected)


def destination(host: str, remote_dir: str) -> str:
    # Restrict remote-shell syntax even though the local subprocess uses argv.
    if not re.fullmatch(r'(?:[A-Za-z0-9_][A-Za-z0-9_.-]*@)?[A-Za-z0-9][A-Za-z0-9_.-]*', host):
        raise ValueError('Use an SSH alias or user@hostname (no shell expressions)')
    if not re.fullmatch(r'/[A-Za-z0-9_./-]+', remote_dir) or '..' in PurePosixPath(remote_dir).parts or remote_dir == '/':
        raise ValueError('Remote directory must be an absolute application path without spaces or ..')
    return f'{host}:{remote_dir.rstrip("/")}/'


def transfer_command(stage: Path, target: str, *, apply: bool) -> list[str]:
    # No --delete: VM secrets, .venv, uploads and previous research data remain intact.
    args = ['rsync', '-rz', '--checksum', '--itemize-changes', '--stats',
            '--chmod=Du=rwx,Dgo=rx,Fu=rw,Fgo=r', '-e', 'ssh -o BatchMode=yes']
    if not apply:
        args.append('--dry-run')
    return [*args, f'{stage}/', target]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', help='Existing SSH alias or user@hostname')
    parser.add_argument('--remote-dir', default='/opt/eten-whatsapp-bot')
    parser.add_argument('--apply', action='store_true', help='Upload; default is a remote dry run')
    parser.add_argument('--list', action='store_true', help='List local payload without connecting')
    args = parser.parse_args()
    if args.apply and args.list:
        parser.error('--list and --apply cannot be combined')
    if not args.list and not args.host:
        parser.error('--host is required unless using --list')
    try:
        target = destination(args.host, args.remote_dir) if args.host else None
        # Rebuild even for previews: a stale dist must not silently enter a deployment.
        subprocess.run(['npm', 'run', 'build'], cwd=ROOT/'platform/frontends/admin', check=True)
        files = select_files(ROOT, ROOT/'deploy/vm-files.txt')
        size = sum((ROOT/path).stat().st_size for path in files)
        print(f'Runtime payload: {len(files)} files, {size / 1024**2:.2f} MiB', flush=True)
        if args.list:
            for path in files:
                print(path.as_posix())
            return 0
        if not shutil.which('rsync'):
            raise ValueError('rsync is required on both the local machine and VM')
        with tempfile.TemporaryDirectory(prefix='eten-vm-') as directory:
            stage = Path(directory)
            for path in files:
                output = stage/path
                output.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT/path, output)
            print('Uploading runtime files.' if args.apply else 'Preview only; nothing will be uploaded.', flush=True)
            subprocess.run(transfer_command(stage, target, apply=args.apply), check=True)
        print('Transfer complete. Dependencies and service restarts are separate steps.' if args.apply
              else 'Preview complete. Add --apply to upload this allowlisted payload.')
        return 0
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f'Deployment stopped: {exc}\n')


if __name__ == '__main__':
    raise SystemExit(main())
