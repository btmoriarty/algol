"""Keep the tools' console output out of a test run.

The tools report on stdout and stderr by design, so tests that call their CLIs
would otherwise scatter that output between the runner's dots. A test module
that drives a CLI imports these as its module fixtures:

    from quiet import silence as setUpModule, restore as tearDownModule  # noqa: F401

The runner reports results on its own stream, captured when it was created, so
failures and tracebacks still show. A test that checks output still redirects
it itself, as before.
"""
from __future__ import annotations

import io
import sys

_saved: list[tuple] = []


def silence() -> None:
    _saved.append((sys.stdout, sys.stderr))
    sys.stdout, sys.stderr = io.StringIO(), io.StringIO()


def restore() -> None:
    sys.stdout, sys.stderr = _saved.pop()
