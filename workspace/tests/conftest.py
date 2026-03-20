"""conftest.py — Shared fixtures for the AgentBeats OfficeQA test suite.

Loads .env before any test session starts, and provides async HTTP client
fixtures for integration testing the FastAPI server.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import AsyncIterator
from unittest.mock import patch

import httpx
import pytest
from asgi_lifespan import LifespanManager

from dotenv import load_dotenv

# Load workspace/.env so GOOGLE_CLOUD_PROJECT and friends are available
# to integration tests regardless of how pytest is invoked.
load_dotenv(Path(__file__).parent.parent / ".env", override=False)


# ---------------------------------------------------------------------------
# anyio backend — required by @pytest.mark.anyio fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def anyio_backend():
    """Use asyncio as the anyio backend for all async tests."""
    return "asyncio"


# ---------------------------------------------------------------------------
# Startup dependency mocking — prevents lifespan from needing real Vertex AI
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_corpus_dir(tmp_path: Path) -> Path:
    """
    Create a temporary corpus directory with a few dummy .txt files.

    Used by mock_startup_deps to satisfy the lifespan corpus-check without
    requiring the real corpus on disk.
    """
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    for i in range(3):
        (corpus / f"doc_{i}.txt").write_text(f"Document {i} content.", encoding="utf-8")
    return corpus


@pytest.fixture()
def mock_startup_deps(tmp_corpus_dir: Path, monkeypatch: pytest.MonkeyPatch):
    """
    Patch environment variables and get_model so the FastAPI lifespan does
    not require real Vertex AI credentials or the production corpus directory.

    Sets:
      GOOGLE_CLOUD_PROJECT=test-project
      CORPUS_DIR=<tmp_corpus_dir>
      MODEL_ID=gemini-test-mock

    Patches src.model_adapter.get_model to return a MagicMock object, avoiding
    any real LLM initialization.
    """
    from unittest.mock import MagicMock

    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
    monkeypatch.setenv("CORPUS_DIR", str(tmp_corpus_dir))
    monkeypatch.setenv("MODEL_ID", "gemini-test-mock")

    with patch("src.model_adapter.get_model", return_value=MagicMock()):
        yield


# ---------------------------------------------------------------------------
# Async HTTP client — httpx.AsyncClient with ASGITransport for FastAPI
# ---------------------------------------------------------------------------


@pytest.fixture()
async def async_client(mock_startup_deps) -> AsyncIterator[httpx.AsyncClient]:
    """
    Yield an httpx.AsyncClient backed by the FastAPI app via ASGITransport.

    Uses asgi_lifespan.LifespanManager to run the app's lifespan (startup and
    shutdown) before handing the client to the test. This ensures _app_state is
    populated by lifespan() before any request is made.

    mock_startup_deps must be applied before this fixture so the lifespan
    checks pass without real Vertex AI credentials.

    Pattern: LifespanManager(app) -> ASGITransport(app=managed_app)
    """
    from src.server import app

    async with LifespanManager(app) as manager:
        transport = httpx.ASGITransport(app=manager.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


# ---------------------------------------------------------------------------
# Agent mock — replaces run_question with a fast, deterministic function
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_run_question(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """
    Patch src.agent.run_question with a deterministic synchronous function.

    The mock:
      1. Creates scratch/<uid>/answer.txt with content "mock_answer_<uid>".
      2. Returns the answer string.

    Uses monkeypatch to patch both src.agent.run_question (the definition)
    and any locally-imported reference, so the endpoint always gets the mock.

    The patch target is src.agent.run_question because server.py imports it
    inside the function body (`from src.agent import run_question`), which
    means each call re-imports — patching at source is therefore correct.

    Returns:
        The mock function (allows call_count inspection in tests).
    """
    from unittest.mock import MagicMock
    from src.scratch import SCRATCH_ROOT

    call_tracker = MagicMock()

    def _mock_run_question(uid: str, question: str) -> str:
        call_tracker(uid, question)
        scratch_dir = SCRATCH_ROOT / uid
        scratch_dir.mkdir(parents=True, exist_ok=True)
        answer = f"mock_answer_{uid}"
        (scratch_dir / "answer.txt").write_text(answer, encoding="utf-8")
        return answer

    _mock_run_question.call_tracker = call_tracker

    monkeypatch.setattr("src.agent.run_question", _mock_run_question)
    return _mock_run_question


# ---------------------------------------------------------------------------
# Scratch directory cleanup — prevents cross-test contamination
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=False)
def clean_scratch():
    """
    Wipe the scratch/ directory before and after each test.

    Not autouse globally — apply to test_server.py tests via
    `pytestmark = [pytest.mark.usefixtures("clean_scratch")]` in that module.
    This prevents cross-question contamination in state isolation tests.
    """
    from src.scratch import SCRATCH_ROOT

    if SCRATCH_ROOT.exists():
        shutil.rmtree(SCRATCH_ROOT)
    SCRATCH_ROOT.mkdir(parents=True, exist_ok=True)

    yield

    if SCRATCH_ROOT.exists():
        shutil.rmtree(SCRATCH_ROOT)
