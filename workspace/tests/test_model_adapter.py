"""
test_model_adapter.py — Unit tests for src/model_adapter.py

All tests are fully offline — no real Vertex AI calls are made.
ChatGoogleGenerativeAI and ChatAnthropicVertex constructors are mocked via
sys.modules injection so the tests work even before langchain packages are
available in the active interpreter.

The new API reads MODEL_ID, GOOGLE_CLOUD_PROJECT, and GOOGLE_CLOUD_LOCATION
directly from environment variables. Tests use monkeypatch or patch to set
these before calling get_model(model_id=...).
"""

from __future__ import annotations

import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


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
        env = {"GOOGLE_CLOUD_PROJECT": "test-project", "GOOGLE_CLOUD_LOCATION": "global"}

        with _MockLangchainModules() as mocks, patch.dict(os.environ, env):
            mock_instance = MagicMock()
            mocks.mock_genai_cls.return_value = mock_instance

            from src.model_adapter import get_model
            result = get_model("gemini-2.0-flash")

        mocks.mock_genai_cls.assert_called_once_with(
            model="gemini-2.0-flash",
            project="test-project",
            location="global",
        )
        assert result is mock_instance
        mocks.mock_anthropic_cls.assert_not_called()

    def test_gemini_pro_prefix_dispatches_to_genai(self):
        env = {"GOOGLE_CLOUD_PROJECT": "test-project", "GOOGLE_CLOUD_LOCATION": "global"}

        with _MockLangchainModules() as mocks, patch.dict(os.environ, env):
            from src.model_adapter import get_model
            get_model("gemini-2.5-pro")

        mocks.mock_genai_cls.assert_called_once()
        call_kwargs = mocks.mock_genai_cls.call_args.kwargs
        assert call_kwargs["model"] == "gemini-2.5-pro"
        mocks.mock_anthropic_cls.assert_not_called()


class TestClaudeDispatch:
    """claude-* model IDs dispatch to ChatAnthropicVertex."""

    def test_claude_prefix_returns_anthropic_instance(self):
        env = {"GOOGLE_CLOUD_PROJECT": "test-project", "GOOGLE_CLOUD_LOCATION": "us-east5"}

        with _MockLangchainModules() as mocks, patch.dict(os.environ, env):
            mock_instance = MagicMock()
            mocks.mock_anthropic_cls.return_value = mock_instance

            from src.model_adapter import get_model
            result = get_model("claude-sonnet-4-6")

        mocks.mock_anthropic_cls.assert_called_once_with(
            model_name="claude-sonnet-4-6",
            project="test-project",
            location="us-east5",
        )
        assert result is mock_instance
        mocks.mock_genai_cls.assert_not_called()

    def test_claude_opus_prefix_dispatches_to_anthropic(self):
        env = {"GOOGLE_CLOUD_PROJECT": "test-project", "GOOGLE_CLOUD_LOCATION": "us-east5"}

        with _MockLangchainModules() as mocks, patch.dict(os.environ, env):
            from src.model_adapter import get_model
            get_model("claude-opus-4")

        mocks.mock_anthropic_cls.assert_called_once()
        call_kwargs = mocks.mock_anthropic_cls.call_args.kwargs
        assert call_kwargs["model_name"] == "claude-opus-4"
        mocks.mock_genai_cls.assert_not_called()


class TestDefaultModelId:
    """Unset MODEL_ID defaults to gemini-2.0-flash, dispatching to ChatGoogleGenerativeAI."""

    def test_default_model_id_dispatches_to_gemini(self):
        env = {
            "GOOGLE_CLOUD_PROJECT": "test-project",
            "GOOGLE_CLOUD_LOCATION": "global",
        }
        # Ensure MODEL_ID is not set
        env_without_model_id = {k: v for k, v in os.environ.items() if k != "MODEL_ID"}
        env_without_model_id.update(env)

        with _MockLangchainModules() as mocks:
            with patch.dict(os.environ, env_without_model_id, clear=True):
                from src.model_adapter import get_model
                get_model(None)

        mocks.mock_genai_cls.assert_called_once()
        call_kwargs = mocks.mock_genai_cls.call_args.kwargs
        assert call_kwargs["model"] == "gemini-2.0-flash"
        mocks.mock_anthropic_cls.assert_not_called()

    def test_model_id_from_env_var_is_used(self):
        env = {
            "MODEL_ID": "gemini-2.5-pro",
            "GOOGLE_CLOUD_PROJECT": "proj",
            "GOOGLE_CLOUD_LOCATION": "global",
        }

        with _MockLangchainModules() as mocks, patch.dict(os.environ, env):
            from src.model_adapter import get_model
            get_model()  # no args — reads from env

        mocks.mock_genai_cls.assert_called_once()
        call_kwargs = mocks.mock_genai_cls.call_args.kwargs
        assert call_kwargs["model"] == "gemini-2.5-pro"


class TestUnsupportedPrefix:
    """Unsupported MODEL_ID prefixes raise ValueError with descriptive message."""

    def test_gpt_prefix_raises_value_error(self):
        with _MockLangchainModules():
            from src.model_adapter import get_model
            with pytest.raises(ValueError, match="gpt-4"):
                get_model("gpt-4")

    def test_error_message_mentions_supported_prefixes(self):
        with _MockLangchainModules():
            from src.model_adapter import get_model
            with pytest.raises(ValueError, match="gemini.*claude"):
                get_model("llama-3")

    def test_empty_model_id_raises_value_error(self):
        with _MockLangchainModules():
            from src.model_adapter import get_model
            with pytest.raises(ValueError):
                get_model("")


class TestProjectAndLocationPassthrough:
    """Project and location values from env are forwarded to the model constructors."""

    def test_project_passed_to_gemini(self):
        env = {
            "GOOGLE_CLOUD_PROJECT": "my-real-project",
            "GOOGLE_CLOUD_LOCATION": "us-central1",
        }

        with _MockLangchainModules() as mocks, patch.dict(os.environ, env):
            from src.model_adapter import get_model
            get_model("gemini-2.0-flash")

        call_kwargs = mocks.mock_genai_cls.call_args.kwargs
        assert call_kwargs["project"] == "my-real-project"
        assert call_kwargs["location"] == "us-central1"

    def test_project_passed_to_claude(self):
        env = {
            "GOOGLE_CLOUD_PROJECT": "another-project",
            "GOOGLE_CLOUD_LOCATION": "europe-west1",
        }

        with _MockLangchainModules() as mocks, patch.dict(os.environ, env):
            from src.model_adapter import get_model
            get_model("claude-sonnet-4-6")

        call_kwargs = mocks.mock_anthropic_cls.call_args.kwargs
        assert call_kwargs["project"] == "another-project"
        assert call_kwargs["location"] == "europe-west1"

    def test_missing_project_env_uses_empty_string(self):
        """GOOGLE_CLOUD_PROJECT not set — passes empty string to constructor."""
        env_without = {k: v for k, v in os.environ.items()
                       if k not in ("GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION")}

        with _MockLangchainModules() as mocks:
            with patch.dict(os.environ, env_without, clear=True):
                from src.model_adapter import get_model
                get_model("gemini-2.0-flash")

        call_kwargs = mocks.mock_genai_cls.call_args.kwargs
        assert call_kwargs["project"] == ""
        assert call_kwargs["location"] == "global"


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
