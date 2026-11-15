"""The program version. The only place it is written is pyproject.toml.

The packaged app ships a copy of pyproject.toml, so the same code works from the source
tree and from the frozen executable.
"""
from __future__ import annotations

import tomllib

from . import paths

APP_NAME = "PQ-SSE Desktop"
COMPANY = "PQ-SSE"
UNKNOWN = "0.0.0"


def get_version() -> str:
    try:
        with open(paths.resource("pyproject.toml"), "rb") as handle:
            return str(tomllib.load(handle)["project"]["version"])
    except (OSError, KeyError, ValueError):
        return UNKNOWN
