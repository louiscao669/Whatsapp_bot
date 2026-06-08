"""Filesystem paths for the monorepo layout (backend/ + frontend/)."""

from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
