"""
test_model_adapter.py — Unit tests for src/model_adapter.py

All tests are fully offline — no real Vertex AI calls are made.
ChatGoogleGenerativeAI and ChatAnthropicVertex constructors are mocked via
sys.modules injection so the tests work even before langchain packages are
available in the active interpreter.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import Config


def _make_config(**kwargs) -> Config:
    """Create a minimal Config suitable for unit tests."""
    defaults = dict(
        model_id="claude-sonnet-4-6",
        google_cloud_project="test-project",
        google_cloud_location="us-east5",
        google_genai_use_vertexai=True,
        google_application_credentials="",
        corpus_source="local",
        corpus_dir=Path("/tmp/corpus"),
        csv_full_path=Path("/tmp/officeqa_full.csv"),
        csv_pro_path=Path("/tmp/officeqa_pro.csv"),
    )
    defaults.update(kwargs)
    return Config(**defaults)


class _MockLangchainModules:
    """
    Context manager that injects mock langchain modules into sys.modules so
    the lazy imports inside get_model() resolve to our mocks instead of the
    real packages.
    """

    def __init__(self):
        self.mock_genai_cls = MagicMock(name="ChatGoogleGenerativeAI")
        self.mock_anthropic_cls = MagicMock(name="ChatAnthropicVertex")
        self._originals: dict[str, object] = {}

    def __enter__(self):
        # Build a fake langchain_google_genai module
        fake_genai = types.ModuleType("langchain_google_genai")
        fake_genai.ChatGoogleGenerativeAI = self.mock_genai_cls
        sys.modules["langchain_google_genai"] = fake_genai

        # Build a fake langchain_google_vertexai.model_garden module
        fake_vertexai = types.ModuleType("langchain_google_vertexai")
        fake_mg = types.ModuleType("langchain_google_vertexai.model_garden")
        fake_mg.ChatAnthropicVertex = self.mock_anthropic_cls
        fake_vertexai.model_garden = fake_mg
        sys.modules["langchain_google_vertexai"] = fake_vertexai
        sys.modules["langchain_google_vertexai.model_garden"] = fake_mg

        # Force reimport of model_adapter so it picks up our mocked modules
        if "src.model_adapter" in sys.modules:
            del sys.modules["src.model_adapter"]

        return self

    def __exit__(self, *args):
        # Clean up injected modules
        for key in ["langchain_google_genai", "langchain_google_vertexai",
                    "langchain_google_vertexai.model_garden", "src.model_adapter"]:
            sys.modules.pop(key, None)


class TestGeminiDispatch:
    """gemini-* model IDs dispatch to ChatGoogleGenerativeAI."""

    def test_gemini_prefix_returns_genai_instance(self):
        config = _make_config(model_id="gemini-2.0-flash", google_cloud_location="global")

        with _MockLangchainModules() as mocks:
            mock_instance = MagicMock()
            mocks.mock_genai_cls.return_value = mock_instance

            from src.model_adapter import get_model
            result = get_model(config)

        mocks.mock_genai_cls.assert_called_once_with(
            model="gemini-2.0-flash",
            project="test-project",
            location="global",
        )
        assert result is mock_instance
        mocks.mock_anthropic_cls.assert_not_called()

    def test_gemini_pro_prefix_dispatches_to_genai(self):
        config = _make_config(model_id="gemini-2.5-pro", google_cloud_location="global")

        with _MockLangchainModules() as mocks:
            from src.model_adapter import get_model
            get_model(config)

        mocks.mock_genai_cls.assert_called_once()
        call_kwargs = mocks.mock_genai_cls.call_args.kwargs
        assert call_kwargs["model"] == "gemini-2.5-pro"
        mocks.mock_anthropic_cls.assert_not_called()


class TestClaudeDispatch:
    """claude-* model IDs dispatch to ChatAnthropicVertex."""

    def test_claude_prefix_returns_anthropic_instance(self):
        config = _make_config(model_id="claude-sonnet-4-6", google_cloud_location="us-east5")

        with _MockLangchainModules() as mocks:
            mock_instance = MagicMock()
            mocks.mock_anthropic_cls.return_value = mock_instance

            from src.model_adapter import get_model
            result = get_model(config)

        mocks.mock_anthropic_cls.assert_called_once_with(
            model_name="claude-sonnet-4-6",
            project="test-project",
            location="us-east5",
        )
        assert result is mock_instance
        mocks.mock_genai_cls.assert_not_called()

    def test_claude_opus_prefix_dispatches_to_anthropic(self):
        config = _make_config(model_id="claude-opus-4", google_cloud_location="us-east5")

        with _MockLangchainModules() as mocks:
            from src.model_adapter import get_model
            get_model(config)

        mocks.mock_anthropic_cls.assert_called_once()
        call_kwargs = mocks.mock_anthropic_cls.call_args.kwargs
        assert call_kwargs["model_name"] == "claude-opus-4"
        mocks.mock_genai_cls.assert_not_called()


class TestDefaultModelId:
    """Unset MODEL_ID defaults to claude-sonnet-4-6, dispatching to ChatAnthropicVertex."""

    def test_default_model_id_dispatches_to_anthropic(self):
        default_config = _make_config(model_id="claude-sonnet-4-6", google_cloud_location="us-east5")

        with _MockLangchainModules() as mocks:
            with patch("src.config.get_config", return_value=default_config):
                from src.model_adapter import get_model
                get_model(None)

        mocks.mock_anthropic_cls.assert_called_once()
        call_kwargs = mocks.mock_anthropic_cls.call_args.kwargs
        assert call_kwargs["model_name"] == "claude-sonnet-4-6"
        mocks.mock_genai_cls.assert_not_called()


class TestUnsupportedPrefix:
    """Unsupported MODEL_ID prefixes raise ValueError with descriptive message."""

    def test_gpt_prefix_raises_value_error(self):
        config = _make_config(model_id="gpt-4")

        with _MockLangchainModules():
            from src.model_adapter import get_model
            with pytest.raises(ValueError, match="gpt-4"):
                get_model(config)

    def test_error_message_mentions_supported_prefixes(self):
        config = _make_config(model_id="llama-3")

        with _MockLangchainModules():
            from src.model_adapter import get_model
            with pytest.raises(ValueError, match="gemini.*claude"):
                get_model(config)

    def test_empty_model_id_raises_value_error(self):
        config = _make_config(model_id="")

        with _MockLangchainModules():
            from src.model_adapter import get_model
            with pytest.raises(ValueError):
                get_model(config)


class TestProjectAndLocationPassthrough:
    """Project and location values are forwarded to the model constructors."""

    def test_project_passed_to_gemini(self):
        config = _make_config(
            model_id="gemini-2.0-flash",
            google_cloud_project="my-real-project",
            google_cloud_location="us-central1",
        )

        with _MockLangchainModules() as mocks:
            from src.model_adapter import get_model
            get_model(config)

        call_kwargs = mocks.mock_genai_cls.call_args.kwargs
        assert call_kwargs["project"] == "my-real-project"
        assert call_kwargs["location"] == "us-central1"

    def test_project_passed_to_claude(self):
        config = _make_config(
            model_id="claude-sonnet-4-6",
            google_cloud_project="another-project",
            google_cloud_location="europe-west1",
        )

        with _MockLangchainModules() as mocks:
            from src.model_adapter import get_model
            get_model(config)

        call_kwargs = mocks.mock_anthropic_cls.call_args.kwargs
        assert call_kwargs["project"] == "another-project"
        assert call_kwargs["location"] == "europe-west1"


@pytest.mark.integration
def test_model_adapter_live_gemini():
    """Live test: real ChatGoogleGenerativeAI instantiation (requires credentials)."""
    from src.model_adapter import get_model
    model = get_model()
    assert model is not None


@pytest.mark.integration
def test_model_adapter_live_claude():
    """Live test: real ChatAnthropicVertex instantiation (requires credentials)."""
    import os
    os.environ["MODEL_ID"] = "claude-sonnet-4-6"
    from src.model_adapter import get_model
    model = get_model()
    assert model is not None
