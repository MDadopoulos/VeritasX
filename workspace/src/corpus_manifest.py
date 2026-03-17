"""
corpus_manifest.py — CSV-derived corpus manifest check.

Parses both benchmark CSVs to build the set of required corpus files,
then validates them against the local corpus directory.

In local mode (CORPUS_SOURCE=local), any missing files are fatal: the process
logs warnings to stderr and exits with code 1.

Key implementation note: the source_files column in both CSVs uses NEWLINE
as the separator between filenames within a quoted cell (not commas). Python's
csv.DictReader handles RFC 4180 quoting correctly, preserving the embedded
newlines. We then split on whitespace after normalising newlines to spaces.
"""

from __future__ import annotations

import csv
import logging
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.config import Config

logger = logging.getLogger(__name__)


def load_manifest(csv_paths: list[str]) -> set[str]:
    """
    Parse the source_files column from each CSV and return unique filenames.

    Args:
        csv_paths: List of paths to CSV files (officeqa_full.csv, officeqa_pro.csv).

    Returns:
        Set of unique basename strings referenced by the source_files columns.

    Note:
        source_files cells may contain multiple filenames separated by newlines
        (embedded within the quoted CSV cell). We replace newlines with spaces
        and split on whitespace to handle both single-file and multi-file cells.
    """
    required: set[str] = set()
    for path in csv_paths:
        with open(path, encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                cell = row.get("source_files", "")
                # Replace embedded newlines with spaces, then split on whitespace.
                # This handles both single-filename cells and multi-filename cells.
                for fname in cell.replace("\n", " ").split():
                    fname = fname.strip()
                    if fname:
                        required.add(fname)
    return required


def validate_corpus(config: "Config | None" = None) -> tuple[set[str], set[str]]:
    """
    Validate that all CSV-referenced corpus files exist on disk.

    Args:
        config: Optional Config instance. If None, get_config() is called.

    Returns:
        Tuple of (required, missing) where both are sets of filename strings.
        required = all unique filenames from both CSVs.
        missing  = filenames in required that are absent from corpus_dir.

    Side effects:
        - Logs "Corpus manifest OK: N files validated" to stderr if no files missing.
        - Logs a WARNING to stderr for each missing file if any are missing.
        - Raises SystemExit(1) if corpus_source == "local" and missing is non-empty.
    """
    if config is None:
        from src.config import get_config
        config = get_config()

    csv_paths = [str(config.csv_full_path), str(config.csv_pro_path)]
    required = load_manifest(csv_paths)

    # Build set of actual filenames present in corpus_dir.
    corpus_dir = Path(config.corpus_dir)
    if corpus_dir.is_dir():
        actual = {f.name for f in corpus_dir.iterdir() if f.is_file()}
    else:
        actual = set()

    missing = required - actual

    if missing:
        for fname in sorted(missing):
            logger.warning("Missing corpus file: %s", fname)
            print(f"WARNING: Missing corpus file: {fname}", file=sys.stderr)
        if config.corpus_source == "local":
            msg = (
                f"Missing {len(missing)} corpus file(s) in local mode — cannot continue. "
                "Ensure all corpus files are present in: " + str(corpus_dir)
            )
            print(f"ERROR: {msg}", file=sys.stderr)
            raise SystemExit(1)
    else:
        msg = f"Corpus manifest OK: {len(required)} files validated"
        logger.info(msg)
        print(msg, file=sys.stderr)

    return (required, missing)
