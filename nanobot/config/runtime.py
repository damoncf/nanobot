"""Helpers for resolving the active nanobot instance paths."""

from __future__ import annotations

import os
from pathlib import Path


def _expand_path(path: str | Path) -> Path:
    """Expand user-relative paths and normalize them against the cwd."""
    return Path(path).expanduser().resolve(strict=False)


def get_instance_home_dir() -> Path:
    """Return the active instance root directory."""
    raw = os.getenv("NANOBOT_HOME")
    if raw:
        return _expand_path(raw)
    raw_config = os.getenv("NANOBOT_CONFIG")
    if raw_config:
        return _expand_path(raw_config).parent
    return Path.home() / ".nanobot"


def get_default_config_path() -> Path:
    """Return the default config path for the active instance."""
    raw = os.getenv("NANOBOT_CONFIG")
    if raw:
        return _expand_path(raw)
    return get_instance_home_dir() / "config.json"


def get_default_workspace_path() -> Path:
    """Return the default workspace path for the active instance."""
    return get_instance_home_dir() / "workspace"
