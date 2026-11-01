"""Load API keys from a local .env file, for runs on the owner's laptop.

Online, keys come from GitHub Actions secrets, which are already environment
variables; there is no .env file there and this does nothing. The code reads
keys only through `os.environ`, never from a file directly.

Rules (CLAUDE.md, Secrets):
- Never print, log or return a value: only variable names leave this module,
  and an error names the line number, never the line.
- Variables already set win, so a stray .env can't replace the real secrets.
- An empty value (as in a fresh copy of .env.example) counts as "not set".

Written with the standard library instead of python-dotenv: the format we need
is just NAME=value lines, so a dependency isn't worth it.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import MutableMapping

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"

_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def load_env(path: Path = ENV_FILE, environ: MutableMapping[str, str] = os.environ) -> list[str]:
    """Copy NAME=value lines from `path` into `environ`. Returns the names that were set."""
    path = Path(path)
    if not path.is_file():
        return []

    loaded = []
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        name, sep, value = line.partition("=")
        name = name.strip()
        if not sep or not _NAME.match(name):
            raise ValueError(f"{path.name}, line {number}: expected NAME=value (content not shown, it may be a secret)")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if not value or name in environ:
            continue
        environ[name] = value
        loaded.append(name)
    return loaded
