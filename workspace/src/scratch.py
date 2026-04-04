"""
scratch.py — Scratch directory lifecycle helpers.

Manages per-question scratch directories under ./scratch/{uid}/ where the
agent writes evidence, tables, extracted values, calculations, verification,
and final answer files.

Public API:
    prepare_scratch(uid)            -> Path   # wipe and recreate ./scratch/{uid}/
    verify_scratch_complete(uid)    -> dict   # check all six expected files exist
    SCRATCH_ROOT                    = Path    # module-level constant
    SCRATCH_FILES                   = list    # expected filenames

All functions return dicts on expected conditions (never raise for missing files).
Input validation raises ValueError for invalid uid.
"""

import os
import shutil
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).parent.parent.parent  # workspace/src/ -> workspace/ -> project root
_DEFAULT_SCRATCH = _PROJECT_ROOT / "agentspace" / "scratch"
SCRATCH_ROOT = Path(os.environ.get("SCRATCH_DIR", str(_DEFAULT_SCRATCH)))

# The six expected scratch files written by the agent during a question run.
SCRATCH_FILES = [
    "evidence.txt",
    "tables.txt",
    "extracted_values.txt",
    "calc.txt",
    "verification.txt",
    "answer.txt",
]


# ---------------------------------------------------------------------------
# Lifecycle helpers
# ---------------------------------------------------------------------------


def prepare_scratch(uid: str) -> Path:
    """
    Wipe and recreate the scratch directory for a question UID.

    If the directory already exists (from a previous run), it is removed
    entirely before recreation. Calling prepare_scratch twice for the same
    UID produces a fresh empty directory each time without error.

    Args:
        uid: Non-empty string identifier for the question run.
             Used as the subdirectory name under SCRATCH_ROOT.

    Returns:
        Path to the freshly created scratch directory (./scratch/{uid}/).

    Raises:
        ValueError: If uid is not a non-empty string.
    """
    if not uid or not isinstance(uid, str):
        raise ValueError(f"uid must be a non-empty string, got {uid!r}")

    scratch_dir = SCRATCH_ROOT / uid

    if scratch_dir.exists():
        shutil.rmtree(scratch_dir)

    scratch_dir.mkdir(parents=True)

    return scratch_dir


def verify_scratch_complete(uid: str) -> dict:
    """
    Check that all six expected scratch files exist and are non-empty.

    Args:
        uid: Question UID identifying the scratch subdirectory.

    Returns:
        {
            "complete": bool,        # True only if all 6 files exist and non-empty
            "missing": list[str],    # filenames not present on disk
            "empty": list[str],      # filenames present but empty (0 bytes)
        }
    """
    scratch_dir = SCRATCH_ROOT / uid
    missing = []
    empty = []

    for fname in SCRATCH_FILES:
        fpath = scratch_dir / fname
        if not fpath.exists():
            missing.append(fname)
        elif fpath.stat().st_size == 0:
            empty.append(fname)

    return {
        "complete": len(missing) == 0 and len(empty) == 0,
        "missing": missing,
        "empty": empty,
    }
