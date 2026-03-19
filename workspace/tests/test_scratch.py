"""
test_scratch.py — Unit tests for src/scratch.py scratch lifecycle helpers.

Tests cover:
  - prepare_scratch: directory creation, wipe-on-rerun, idempotent calls
  - prepare_scratch: input validation (empty uid raises ValueError)
  - verify_scratch_complete: all-missing, all-present, and partial-empty cases
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.scratch import SCRATCH_FILES, prepare_scratch, verify_scratch_complete


# ---------------------------------------------------------------------------
# prepare_scratch tests
# ---------------------------------------------------------------------------


def test_prepare_scratch_creates_directory(tmp_path, monkeypatch):
    """prepare_scratch(uid) creates a new directory and returns the Path."""
    import src.scratch as scratch_mod

    monkeypatch.setattr(scratch_mod, "SCRATCH_ROOT", tmp_path / "scratch")

    uid = "unit_test_uid"
    result = prepare_scratch(uid)

    assert result.exists(), "Returned path must exist"
    assert result.is_dir(), "Returned path must be a directory"
    assert result.name == uid


def test_prepare_scratch_wipes_existing(tmp_path, monkeypatch):
    """prepare_scratch(uid) removes existing content before recreating (SCR-01)."""
    import src.scratch as scratch_mod

    scratch_root = tmp_path / "scratch"
    monkeypatch.setattr(scratch_mod, "SCRATCH_ROOT", scratch_root)

    uid = "wipe_test_uid"
    # First call — creates directory
    scratch_dir = prepare_scratch(uid)

    # Write a file into it
    sentinel = scratch_dir / "old_file.txt"
    sentinel.write_text("old content")
    assert sentinel.exists(), "Sentinel file should exist before second call"

    # Second call — should wipe and recreate
    result = prepare_scratch(uid)

    assert result.exists(), "Directory must exist after second call"
    assert result.is_dir(), "Must still be a directory"
    assert not sentinel.exists(), "Old file must be gone after wipe"


def test_prepare_scratch_idempotent(tmp_path, monkeypatch):
    """Calling prepare_scratch twice with the same uid raises no error (success criterion 3)."""
    import src.scratch as scratch_mod

    monkeypatch.setattr(scratch_mod, "SCRATCH_ROOT", tmp_path / "scratch")

    uid = "idempotent_uid"
    result_1 = prepare_scratch(uid)
    result_2 = prepare_scratch(uid)

    # Both calls succeed and the directory exists
    assert result_1.name == uid
    assert result_2.name == uid
    assert result_2.exists()
    assert result_2.is_dir()


def test_prepare_scratch_empty_uid_raises():
    """prepare_scratch('') raises ValueError for empty uid."""
    with pytest.raises(ValueError, match="non-empty string"):
        prepare_scratch("")


# ---------------------------------------------------------------------------
# verify_scratch_complete tests
# ---------------------------------------------------------------------------


def test_verify_scratch_complete_all_missing(tmp_path, monkeypatch):
    """verify_scratch_complete on empty dir returns complete=False with all 6 filenames missing."""
    import src.scratch as scratch_mod

    scratch_root = tmp_path / "scratch"
    monkeypatch.setattr(scratch_mod, "SCRATCH_ROOT", scratch_root)

    uid = "all_missing_uid"
    # Create empty directory (no files inside)
    (scratch_root / uid).mkdir(parents=True)

    result = verify_scratch_complete(uid)

    assert result["complete"] is False
    assert set(result["missing"]) == set(SCRATCH_FILES), (
        f"All 6 filenames must be reported missing, got: {result['missing']}"
    )
    assert result["empty"] == []


def test_verify_scratch_complete_all_present(tmp_path, monkeypatch):
    """verify_scratch_complete with all 6 non-empty files returns complete=True."""
    import src.scratch as scratch_mod

    scratch_root = tmp_path / "scratch"
    monkeypatch.setattr(scratch_mod, "SCRATCH_ROOT", scratch_root)

    uid = "all_present_uid"
    scratch_dir = scratch_root / uid
    scratch_dir.mkdir(parents=True)

    # Write non-empty content to all 6 files
    for fname in SCRATCH_FILES:
        (scratch_dir / fname).write_text(f"content for {fname}")

    result = verify_scratch_complete(uid)

    assert result["complete"] is True
    assert result["missing"] == []
    assert result["empty"] == []


def test_verify_scratch_complete_empty_file(tmp_path, monkeypatch):
    """verify_scratch_complete with one empty file returns complete=False and reports it in empty."""
    import src.scratch as scratch_mod

    scratch_root = tmp_path / "scratch"
    monkeypatch.setattr(scratch_mod, "SCRATCH_ROOT", scratch_root)

    uid = "empty_file_uid"
    scratch_dir = scratch_root / uid
    scratch_dir.mkdir(parents=True)

    # Write all 6 files — leave calc.txt empty
    empty_file = "calc.txt"
    for fname in SCRATCH_FILES:
        if fname == empty_file:
            (scratch_dir / fname).write_text("")
        else:
            (scratch_dir / fname).write_text(f"content for {fname}")

    result = verify_scratch_complete(uid)

    assert result["complete"] is False
    assert result["missing"] == []
    assert empty_file in result["empty"], (
        f"'{empty_file}' must appear in empty list, got: {result['empty']}"
    )
