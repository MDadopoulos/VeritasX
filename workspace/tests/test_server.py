"""
test_server.py — Integration tests for the A2A HTTP server.

Tests cover:
  TST-05: 10 sample questions all return HTTP 200 with {uid, answer} schema
  TST-06: State isolation — no cross-UID contamination in scratch files
  HTTP-03: Idempotency — same uid returns cached answer without re-running agent
  HTTP-03+: Force bypass — ?force=true re-runs the agent despite cache
  Error: Missing uid → 422 with custom shape {reason}
  Error: Wrong field type → 422 with {uid, reason}
  Error: Empty body → 422 with {reason}
  Timeout: Slow agent → 504 with {uid, reason}
  Health: GET /health → 200 with {status, corpus_files, model_id, credentials}

All tests use mocked agent — no Vertex AI credentials needed.
"""
from __future__ import annotations

import asyncio
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

# ---------------------------------------------------------------------------
# Module-level mark: apply clean_scratch and async backend to all tests here
# ---------------------------------------------------------------------------

pytestmark = [
    pytest.mark.anyio,
    pytest.mark.usefixtures("clean_scratch"),
]

# ---------------------------------------------------------------------------
# Sample questions for TST-05 (10-question schema validation)
# ---------------------------------------------------------------------------

SAMPLE_QUESTIONS = [
    {"uid": "UID0001", "question": "What were total expenditures for U.S. national defense in 1940?"},
    {"uid": "UID0002", "question": "What was the total public debt at the end of June 1945?"},
    {"uid": "UID0003", "question": "What were total internal revenue collections in 1942?"},
    {"uid": "UID0004", "question": "What was the percent change in defense spending from 1940 to 1941?"},
    {"uid": "UID0005", "question": "How much did the Treasury spend on interest on the public debt in FY1943?"},
    {"uid": "UID0006", "question": "What were total customs receipts in calendar year 1939?"},
    {"uid": "UID0007", "question": "What was gross national product in 1944?"},
    {"uid": "UID0008", "question": "How much gold was held by the Treasury at end of 1941?"},
    {"uid": "UID0009", "question": "What were total expenditures of the federal government in FY1942?"},
    {"uid": "UID0010", "question": "What was the average yield on Treasury bonds in December 1940?"},
]


# ---------------------------------------------------------------------------
# TST-05: Schema validation across 10 sample questions
# ---------------------------------------------------------------------------


async def test_run_10_questions_schema(async_client: httpx.AsyncClient, mock_run_question):
    """
    POST each of the 10 SAMPLE_QUESTIONS to /run.

    Asserts:
      - Each returns HTTP 200.
      - Response JSON has exactly two keys: "uid" and "answer".
      - Response uid matches request uid.
      - Response answer is a non-empty string.
    """
    for item in SAMPLE_QUESTIONS:
        response = await async_client.post("/run", json=item)
        assert response.status_code == 200, (
            f"Expected 200 for uid={item['uid']}, got {response.status_code}: {response.text}"
        )
        data = response.json()
        assert set(data.keys()) == {"uid", "answer"}, (
            f"Response for uid={item['uid']} has unexpected keys: {data.keys()}"
        )
        assert data["uid"] == item["uid"], (
            f"Response uid mismatch: expected {item['uid']!r}, got {data['uid']!r}"
        )
        assert isinstance(data["answer"], str) and data["answer"], (
            f"Response answer for uid={item['uid']} is empty or not a string: {data['answer']!r}"
        )


# ---------------------------------------------------------------------------
# HTTP-03: Idempotency — same uid returns cached answer (agent called once)
# ---------------------------------------------------------------------------


async def test_idempotency_same_uid(async_client: httpx.AsyncClient, mock_run_question):
    """
    POST the same uid twice. Assert second response returns cached answer.
    The mock must be called only ONCE (second request hits the cache).
    """
    payload = {"uid": "IDEM_TEST_001", "question": "What were defense expenditures in 1940?"}

    first = await async_client.post("/run", json=payload)
    assert first.status_code == 200
    first_answer = first.json()["answer"]

    second = await async_client.post("/run", json=payload)
    assert second.status_code == 200
    second_answer = second.json()["answer"]

    # Answers must be identical
    assert first_answer == second_answer, (
        f"Idempotency violated: first={first_answer!r}, second={second_answer!r}"
    )

    # Mock was only called once — second request hit the cache
    assert mock_run_question.call_tracker.call_count == 1, (
        f"Expected agent called once, was called {mock_run_question.call_tracker.call_count} times"
    )


# ---------------------------------------------------------------------------
# HTTP-03+: Force bypass — ?force=true re-runs agent regardless of cache
# ---------------------------------------------------------------------------


async def test_idempotency_force_bypass(async_client: httpx.AsyncClient, mock_run_question):
    """
    POST uid once (caches answer), then POST same uid with ?force=true.
    Assert the mock is called TWICE — force bypasses cache.
    """
    payload = {"uid": "FORCE_TEST_001", "question": "What was the public debt in 1945?"}

    first = await async_client.post("/run", json=payload)
    assert first.status_code == 200

    second = await async_client.post("/run?force=true", json=payload)
    assert second.status_code == 200

    # Mock called twice — once for first run, once for forced re-run
    assert mock_run_question.call_tracker.call_count == 2, (
        f"Expected agent called twice with force=true, was called {mock_run_question.call_tracker.call_count} times"
    )


# ---------------------------------------------------------------------------
# TST-06: State isolation — no cross-UID contamination in scratch files
# ---------------------------------------------------------------------------


async def test_state_isolation(async_client: httpx.AsyncClient, mock_run_question):
    """
    Run two questions with disjoint UIDs sequentially.
    Assert that no file in scratch/uid_b/ contains uid_a or uid_a's answer.
    """
    from src.scratch import SCRATCH_ROOT

    uid_a = "ISO_A"
    uid_b = "ISO_B"

    response_a = await async_client.post(
        "/run", json={"uid": uid_a, "question": "What were defense expenditures?"}
    )
    assert response_a.status_code == 200

    response_b = await async_client.post(
        "/run", json={"uid": uid_b, "question": "What was total public debt?"}
    )
    assert response_b.status_code == 200

    answer_a = response_a.json()["answer"]

    # Inspect scratch/ISO_B/ for any trace of uid_a or its answer
    scratch_b = SCRATCH_ROOT / uid_b
    assert scratch_b.exists(), f"scratch/{uid_b}/ was not created"

    contamination_found = []
    for fpath in scratch_b.iterdir():
        if fpath.is_file():
            content = fpath.read_text(encoding="utf-8")
            if uid_a in content:
                contamination_found.append(f"{fpath.name}: contains uid_a={uid_a!r}")
            if answer_a in content:
                contamination_found.append(f"{fpath.name}: contains answer_a={answer_a!r}")

    assert not contamination_found, (
        f"Cross-UID contamination in scratch/{uid_b}/:\n" + "\n".join(contamination_found)
    )


# ---------------------------------------------------------------------------
# Error: Missing uid → 422 with custom shape
# ---------------------------------------------------------------------------


async def test_invalid_request_422_missing_uid(async_client: httpx.AsyncClient, mock_run_question):
    """
    POST with body missing uid field.
    Assert 422 with custom shape: {"reason": ...} without "detail" key.
    """
    response = await async_client.post("/run", json={"question": "no uid here"})
    assert response.status_code == 422, f"Expected 422, got {response.status_code}"
    data = response.json()
    assert "reason" in data, f"Missing 'reason' key in 422 response: {data}"
    assert "detail" not in data, (
        f"422 response has FastAPI default 'detail' key instead of custom shape: {data}"
    )


# ---------------------------------------------------------------------------
# Error: Wrong type for question → 422 with uid echoed back
# ---------------------------------------------------------------------------


async def test_invalid_request_422_with_uid(async_client: httpx.AsyncClient, mock_run_question):
    """
    POST with uid present but question has wrong type (int instead of str).
    Assert 422 with {"uid": "BAD001", "reason": ...}.
    """
    response = await async_client.post("/run", json={"uid": "BAD001", "question": 12345})
    assert response.status_code == 422, f"Expected 422, got {response.status_code}"
    data = response.json()
    assert "reason" in data, f"Missing 'reason' key in 422 response: {data}"
    assert data.get("uid") == "BAD001", (
        f"Expected uid='BAD001' echoed in 422 response, got: {data}"
    )


# ---------------------------------------------------------------------------
# Error: Empty body → 422 with reason
# ---------------------------------------------------------------------------


async def test_empty_body_422(async_client: httpx.AsyncClient, mock_run_question):
    """
    POST to /run with empty body (Content-Type: application/json but no body).
    Assert 422 with "reason" key — not FastAPI default "detail".
    """
    response = await async_client.post(
        "/run",
        content=b"",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422, f"Expected 422, got {response.status_code}"
    data = response.json()
    assert "reason" in data, f"Missing 'reason' key in 422 response: {data}"


# ---------------------------------------------------------------------------
# Health endpoint — GET /health returns expected fields
# ---------------------------------------------------------------------------


async def test_health_endpoint(async_client: httpx.AsyncClient):
    """
    GET /health returns 200 with {status, corpus_files, model_id, credentials}.
    status must be "ok", corpus_files must be an integer >= 0.
    """
    response = await async_client.get("/health")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    data = response.json()

    required_keys = {"status", "corpus_files", "model_id", "credentials"}
    assert required_keys <= set(data.keys()), (
        f"Health response missing keys. Expected {required_keys}, got {set(data.keys())}"
    )
    assert data["status"] == "ok", f"Expected status='ok', got {data['status']!r}"
    assert isinstance(data["corpus_files"], int) and data["corpus_files"] >= 0, (
        f"corpus_files must be a non-negative integer, got {data['corpus_files']!r}"
    )


# ---------------------------------------------------------------------------
# Timeout: slow agent → 504 with {uid, reason}
# ---------------------------------------------------------------------------


async def test_agent_timeout_504(async_client: httpx.AsyncClient, mock_startup_deps, monkeypatch):
    """
    When the agent takes longer than AGENT_TIMEOUT_SECONDS, /run returns 504.
    Assert response JSON has {uid, reason} where reason contains "timed out".

    Strategy:
      1. Set a very short timeout (0.05s) via monkeypatch on _app_state.
      2. Replace run_question with a slow mock that sleeps for 2s.
      3. POST a valid request — expect 504.
    """
    from src.server import _app_state
    from src.scratch import SCRATCH_ROOT

    def _slow_run_question(uid: str, question: str) -> str:
        # Sleep long enough to exceed the patched timeout
        time.sleep(2)
        return "too late"

    # Patch the agent call — must patch at source since server imports it at call time
    with patch("src.agent.run_question", side_effect=_slow_run_question):
        # Set a very short timeout to trigger 504 quickly
        original_timeout = _app_state.get("agent_timeout", 300)
        _app_state["agent_timeout"] = 0.05

        try:
            payload = {"uid": "TIMEOUT_TEST_001", "question": "What was defense spending?"}
            response = await async_client.post("/run", json=payload, timeout=10.0)
        finally:
            _app_state["agent_timeout"] = original_timeout

    assert response.status_code == 504, (
        f"Expected 504 for timed-out agent, got {response.status_code}: {response.text}"
    )
    data = response.json()
    assert "uid" in data, f"504 response missing 'uid': {data}"
    assert data["uid"] == "TIMEOUT_TEST_001", (
        f"504 response uid mismatch: {data['uid']!r}"
    )
    assert "reason" in data, f"504 response missing 'reason': {data}"
    assert "timed out" in data["reason"].lower(), (
        f"Expected 'timed out' in reason, got: {data['reason']!r}"
    )
