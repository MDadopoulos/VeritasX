"""
test_config.py — Unit tests for src/config.py

All tests are fully offline — no real GCP credentials needed.
Uses monkeypatch to manipulate environment variables.
"""

import os
from pathlib import Path

import pytest

# Ensure the workspace/src directory is importable when running pytest from workspace/
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestDefaultModelId:
    """MODEL_ID defaults to claude-sonnet-4-6 when not set."""

    def test_default_model_id(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
        monkeypatch.delenv("MODEL_ID", raising=False)

        from src.config import get_config
        config = get_config()

        assert config.model_id == "claude-sonnet-4-6"


class TestMissingGoogleCloudProject:
    """RuntimeError is raised when GOOGLE_CLOUD_PROJECT is not set."""

    def test_missing_project_raises_runtime_error(self, monkeypatch):
        monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)

        from src.config import get_config

        with pytest.raises(RuntimeError, match="GOOGLE_CLOUD_PROJECT"):
            get_config()

    def test_empty_project_raises_runtime_error(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "")

        from src.config import get_config

        with pytest.raises(RuntimeError, match="GOOGLE_CLOUD_PROJECT"):
            get_config()


class TestCustomEnvVars:
    """Custom env var values are picked up correctly."""

    def test_custom_model_id(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
        monkeypatch.setenv("MODEL_ID", "gemini-2.0-flash")

        from src.config import get_config
        config = get_config()

        assert config.model_id == "gemini-2.0-flash"

    def test_custom_location(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
        monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "us-east5")

        from src.config import get_config
        config = get_config()

        assert config.google_cloud_location == "us-east5"

    def test_custom_corpus_source(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
        monkeypatch.setenv("CORPUS_SOURCE", "remote")

        from src.config import get_config
        config = get_config()

        assert config.corpus_source == "remote"

    def test_google_cloud_project_is_read(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "my-gcp-project")

        from src.config import get_config
        config = get_config()

        assert config.google_cloud_project == "my-gcp-project"

    def test_google_application_credentials_is_read(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
        monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/path/to/creds.json")

        from src.config import get_config
        config = get_config()

        assert config.google_application_credentials == "/path/to/creds.json"

    def test_google_genai_use_vertexai_false(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
        monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "false")

        from src.config import get_config
        config = get_config()

        assert config.google_genai_use_vertexai is False

    def test_google_genai_use_vertexai_true(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
        monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "true")

        from src.config import get_config
        config = get_config()

        assert config.google_genai_use_vertexai is True


class TestPathResolution:
    """Paths are resolved to absolute paths using pathlib."""

    def test_corpus_dir_is_absolute(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
        monkeypatch.setenv("CORPUS_DIR", "../corpus/transformed")

        from src.config import get_config
        config = get_config()

        assert config.corpus_dir.is_absolute()

    def test_csv_full_path_is_absolute(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
        monkeypatch.setenv("CSV_FULL_PATH", "../officeqa_full.csv")

        from src.config import get_config
        config = get_config()

        assert config.csv_full_path.is_absolute()

    def test_csv_pro_path_is_absolute(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
        monkeypatch.setenv("CSV_PRO_PATH", "../officeqa_pro.csv")

        from src.config import get_config
        config = get_config()

        assert config.csv_pro_path.is_absolute()

    def test_custom_corpus_dir_resolves(self, monkeypatch, tmp_path):
        monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
        monkeypatch.setenv("CORPUS_DIR", str(tmp_path))

        from src.config import get_config
        config = get_config()

        assert config.corpus_dir == tmp_path.resolve()

    def test_custom_csv_paths_resolve(self, monkeypatch, tmp_path):
        monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
        fake_csv = tmp_path / "test.csv"
        monkeypatch.setenv("CSV_FULL_PATH", str(fake_csv))
        monkeypatch.setenv("CSV_PRO_PATH", str(fake_csv))

        from src.config import get_config
        config = get_config()

        assert config.csv_full_path == fake_csv.resolve()
        assert config.csv_pro_path == fake_csv.resolve()
