# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2026 Jon R. Fox
"""Where the third-party model corpora live.

The library itself never reads a corpus. The check suites and the module
generators do, and each of them used to spell out one absolute path, so a
clone carried a mount point that exists on exactly one machine. The
location comes from UMLMETA_CORPUS instead:

    export UMLMETA_CORPUS=/path/to/models

With the variable unset the root is ~/uml-corpus; on the machine where the
files were first collected, /mnt/TBFox is used if it happens to exist, so
existing setups keep working without a change. Every suite that needs a
corpus skips when the file is not there, so everything that does not need one
still runs on a machine that has never seen these files. Set UMLMETA_STRICT=1
to turn that skip into an error: a run that claims to cover the corpus should
not pass by finding nothing.
"""
import os
import sys
from pathlib import Path

ENV = "UMLMETA_CORPUS"
STRICT_ENV = "UMLMETA_STRICT"
DEFAULT_ROOT = Path.home() / "uml-corpus"
LEGACY_ROOT = Path("/mnt/TBFox")

__all__ = ["ENV", "STRICT_ENV", "DEFAULT_ROOT", "LEGACY_ROOT", "root", "path",
           "available", "available_all", "missing", "finish_skipped", "strict"]


def root():
    """The corpus directory: $UMLMETA_CORPUS, else where the files are.

    A clone has no corpus. The collected tree is named by the environment
    variable; failing that, the historical mount is honoured if it is really
    there, and otherwise ~/uml-corpus is named so the skip message is useful.
    """
    env = os.environ.get(ENV)
    if env:
        return Path(env)
    if LEGACY_ROOT.is_dir():
        return LEGACY_ROOT
    return DEFAULT_ROOT


def path(*parts):
    """A path inside the corpus directory."""
    return root().joinpath(*parts)


def available(p):
    """True when a corpus path exists (file or directory)."""
    return Path(p).exists()


def available_all(paths):
    return all(available(p) for p in paths)


def missing(what, p=None):
    """Print a SKIP line and return True when the corpus path is absent."""
    p = root() if p is None else Path(p)
    if available(p):
        return False
    print(f"  SKIP  {what} not on disk ({p}); set {ENV}")
    return True


def finish_skipped(passed, failed, what, p=None):
    """Report an absent corpus as a skip: exit 0, or 1 under UMLMETA_STRICT."""
    missing(what, p)
    if strict():
        print(f"\nERROR: {what} missing and {STRICT_ENV} is set")
        sys.exit(1)
    print(f"\nRESULT: {passed} passed, {failed} failed (corpus skipped)")
    sys.exit(0)


def strict():
    """True when a missing corpus must fail rather than skip."""
    return os.environ.get(STRICT_ENV, "").strip().lower() not in (
        "", "0", "no", "false")
