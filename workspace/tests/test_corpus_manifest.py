"""
test_corpus_manifest.py — Unit tests for src/corpus_manifest.py

Tests cover:
  - load_manifest correctly parses newline-separated source_files from real CSVs
  - manifest returns exactly 285 unique files across both CSVs
  - validate_corpus with real corpus dir reports zero missing files
  - validate_corpus with a temp dir missing one file raises SystemExit in local mode
  - single-file source_files cell parses correctly
  - multi-file newline-separated cell parses correctly

Real CSV files (officeqa_full.csv, officeqa_pro.csv) are used for manifest tests.
The corpus dir validation uses the real corpus directory.
tmp_path is used for the missing-file test to avoid modifying real corpus.
"""

from __future__ import annotations

import csv
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.corpus_manifest import load_manifest, validate_corpus
from src.config import Config

# Paths relative to this test file (workspace/tests/) — go up two levels to repo root.
REPO_ROOT = Path(__file__).parent.parent.parent  # LucidOwlF/
CSV_FULL = REPO_ROOT / "officeqa_full.csv"
CSV_PRO = REPO_ROOT / "officeqa_pro.csv"
CORPUS_DIR = REPO_ROOT / "corpus" / "transformed"


def _make_config(**kwargs) -> Config:
    """Create a Config for tests, overriding with kwargs."""
    defaults = dict(
        model_id="claude-sonnet-4-6",
        google_cloud_project="test-project",
        google_cloud_location="us-east5",
        google_genai_use_vertexai=True,
        google_application_credentials="",
        corpus_source="local",
        corpus_dir=CORPUS_DIR,
        csv_full_path=CSV_FULL,
        csv_pro_path=CSV_PRO,
    )
    defaults.update(kwargs)
    return Config(**defaults)


class TestLoadManifestWithRealCSVs:
    """load_manifest parses the real CSV files correctly."""

    def test_manifest_returns_285_unique_files(self):
        manifest = load_manifest([str(CSV_FULL), str(CSV_PRO)])
        assert len(manifest) == 285, (
            f"Expected 285 unique source files, got {len(manifest)}"
        )

    def test_manifest_returns_set(self):
        manifest = load_manifest([str(CSV_FULL), str(CSV_PRO)])
        assert isinstance(manifest, set)

    def test_manifest_contains_known_file(self):
        manifest = load_manifest([str(CSV_FULL), str(CSV_PRO)])
        # We know from corpus inspection that this file is referenced.
        assert "treasury_bulletin_1941_01.txt" in manifest

    def test_manifest_entries_are_txt_filenames(self):
        manifest = load_manifest([str(CSV_FULL), str(CSV_PRO)])
        for fname in manifest:
            assert fname.endswith(".txt"), f"Non-.txt entry in manifest: {fname!r}"
            assert "\n" not in fname, f"Newline found in manifest entry: {fname!r}"
            assert " " not in fname, f"Space found in manifest entry: {fname!r}"

    def test_single_csv_returns_subset(self):
        full_only = load_manifest([str(CSV_FULL)])
        both = load_manifest([str(CSV_FULL), str(CSV_PRO)])
        assert full_only.issubset(both), "Files from full CSV alone should be a subset of combined"

    def test_empty_csv_path_list_returns_empty_set(self):
        result = load_manifest([])
        assert result == set()


class TestSourceFilesParsingEdgeCases:
    """Parsing of single-file and multi-file source_files cells."""

    def test_single_file_cell_parses_correctly(self, tmp_path):
        csv_file = tmp_path / "test.csv"
        csv_file.write_text(
            "uid,question,answer,source_files\n"
            "1,q,a,treasury_bulletin_1941_01.txt\n",
            encoding="utf-8",
        )
        result = load_manifest([str(csv_file)])
        assert result == {"treasury_bulletin_1941_01.txt"}

    def test_multi_file_newline_separated_cell_parses_correctly(self, tmp_path):
        csv_file = tmp_path / "test.csv"
        # Write a CSV with an embedded newline in the source_files cell (RFC 4180 quoted)
        content = (
            "uid,question,answer,source_files\n"
            '1,q,a,"treasury_bulletin_1941_01.txt\ntreasury_bulletin_1941_02.txt"\n'
        )
        csv_file.write_text(content, encoding="utf-8")
        result = load_manifest([str(csv_file)])
        assert result == {
            "treasury_bulletin_1941_01.txt",
            "treasury_bulletin_1941_02.txt",
        }

    def test_three_file_newline_separated_cell(self, tmp_path):
        csv_file = tmp_path / "test.csv"
        content = (
            "uid,question,answer,source_files\n"
            '1,q,a,"a.txt\nb.txt\nc.txt"\n'
        )
        csv_file.write_text(content, encoding="utf-8")
        result = load_manifest([str(csv_file)])
        assert result == {"a.txt", "b.txt", "c.txt"}

    def test_empty_source_files_cell_skipped(self, tmp_path):
        csv_file = tmp_path / "test.csv"
        csv_file.write_text(
            "uid,question,answer,source_files\n"
            "1,q,a,\n",
            encoding="utf-8",
        )
        result = load_manifest([str(csv_file)])
        assert result == set()

    def test_multiple_rows_deduplication(self, tmp_path):
        csv_file = tmp_path / "test.csv"
        csv_file.write_text(
            "uid,question,answer,source_files\n"
            "1,q1,a1,bulletin_a.txt\n"
            "2,q2,a2,bulletin_a.txt\n"
            "3,q3,a3,bulletin_b.txt\n",
            encoding="utf-8",
        )
        result = load_manifest([str(csv_file)])
        assert result == {"bulletin_a.txt", "bulletin_b.txt"}


class TestValidateCorpusWithRealData:
    """validate_corpus passes with the real corpus directory."""

    def test_real_corpus_has_zero_missing_files(self, capsys):
        config = _make_config()
        required, missing = validate_corpus(config)

        assert len(missing) == 0, f"Unexpected missing files: {missing}"
        assert len(required) == 285

        captured = capsys.readouterr()
        assert "Corpus manifest OK" in captured.err

    def test_returns_tuple_of_sets(self):
        config = _make_config()
        result = validate_corpus(config)

        assert isinstance(result, tuple)
        assert len(result) == 2
        required, missing = result
        assert isinstance(required, set)
        assert isinstance(missing, set)


class TestValidateCorpusMissingFiles:
    """validate_corpus raises SystemExit(1) in local mode when files are missing."""

    def test_missing_file_raises_system_exit_in_local_mode(self, tmp_path, capsys):
        # Create a corpus dir with only SOME files (missing at least one required file)
        fake_corpus = tmp_path / "corpus"
        fake_corpus.mkdir()

        # Get the full manifest to know which files are required
        manifest = load_manifest([str(CSV_FULL), str(CSV_PRO)])
        # Put all but one file in the fake corpus (as empty files)
        files_list = sorted(manifest)
        for fname in files_list[:-1]:  # all except last
            (fake_corpus / fname).write_text("", encoding="utf-8")

        missing_file = files_list[-1]

        config = _make_config(corpus_source="local", corpus_dir=fake_corpus)

        with pytest.raises(SystemExit) as exc_info:
            validate_corpus(config)

        assert exc_info.value.code == 1

        captured = capsys.readouterr()
        assert missing_file in captured.err

    def test_missing_file_logs_warning_to_stderr(self, tmp_path, capsys):
        fake_corpus = tmp_path / "corpus"
        fake_corpus.mkdir()
        # Leave the corpus empty — all 285 files will be missing

        config = _make_config(corpus_source="local", corpus_dir=fake_corpus)

        with pytest.raises(SystemExit):
            validate_corpus(config)

        captured = capsys.readouterr()
        assert "WARNING" in captured.err or "Missing corpus file" in captured.err

    def test_missing_files_in_non_local_mode_does_not_raise(self, tmp_path, capsys):
        """In non-local corpus_source mode, missing files should NOT raise SystemExit."""
        fake_corpus = tmp_path / "corpus"
        fake_corpus.mkdir()
        # Leave empty — all files missing, but corpus_source is not "local"

        config = _make_config(corpus_source="remote", corpus_dir=fake_corpus)

        # Should NOT raise SystemExit
        required, missing = validate_corpus(config)
        assert len(missing) > 0  # files are genuinely missing
        # But no SystemExit was raised

    def test_nonexistent_corpus_dir_in_local_mode_exits(self, tmp_path):
        fake_corpus = tmp_path / "does_not_exist"
        config = _make_config(corpus_source="local", corpus_dir=fake_corpus)

        with pytest.raises(SystemExit) as exc_info:
            validate_corpus(config)

        assert exc_info.value.code == 1


@pytest.mark.integration
def test_validate_corpus_live():
    """Live test: validates the real corpus with real config (requires corpus in place)."""
    required, missing = validate_corpus()
    assert len(missing) == 0
    assert len(required) == 285
