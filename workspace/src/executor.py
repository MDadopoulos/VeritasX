"""
executor.py — A2A AgentExecutor wrapping the existing run_question() pipeline.

Bridges the A2A protocol (RequestContext, EventQueue) to the synchronous
run_question() entry point. Uses asyncio.to_thread() to avoid blocking
the event loop. Carries forward idempotency cache and concurrency control
from the Phase 5 FastAPI server.
"""

from __future__ import annotations

import asyncio
import logging
from uuid import uuid4

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import UnsupportedOperationError
from a2a.utils import new_agent_text_message

logger = logging.getLogger(__name__)


class OfficeQAAgentExecutor(AgentExecutor):
    """
    A2A executor that delegates to run_question() in a thread pool.

    Lifecycle:
    1. Extract question text from A2A message via context.get_user_input()
    2. Derive uid from context.task_id (or generate UUID)
    3. Check idempotency cache (scratch/{uid}/answer.txt)
    4. Acquire semaphore slot for concurrency control
    5. Call run_question(uid, question) via asyncio.to_thread()
    6. Enqueue answer as agent text message
    """

    def __init__(self, max_concurrent: int = 4, timeout: float = 3000.0):
        self._semaphore: asyncio.Semaphore | None = None
        self._max_concurrent = max_concurrent
        self._timeout = timeout

    def _ensure_semaphore(self) -> None:
        """Lazy-create semaphore inside the running event loop."""
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self._max_concurrent)

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        from src.agent import run_question

        self._ensure_semaphore()

        # Extract question text using the SDK helper (handles TextPart structure)
        question = context.get_user_input()
        if not question:
            raise ValueError("No text content found in A2A message")

        # Derive uid: prefer task_id, fall back to message contextId, then UUID
        uid = context.task_id
        if not uid:
            msg = context.message
            uid = (
                getattr(msg, "context_id", None)
                or getattr(msg, "message_id", None)
                or str(uuid4())
            )

        # Idempotency: check cache before running
        cached = self._get_cached_answer(uid)
        if cached is not None:
            logger.info("Returning cached answer for uid=%s", uid)
            await event_queue.enqueue_event(new_agent_text_message(cached))
            return

        # Concurrency control + timeout
        async with self._semaphore:  # type: ignore[union-attr]
            try:
                answer = await asyncio.wait_for(
                    asyncio.to_thread(run_question, uid, question),
                    timeout=self._timeout,
                )
            except asyncio.TimeoutError:
                logger.error(
                    "Agent timed out after %.0fs for uid=%s", self._timeout, uid
                )
                raise
            except Exception:
                logger.error("Agent crashed for uid=%s", uid, exc_info=True)
                raise

        await event_queue.enqueue_event(new_agent_text_message(answer))

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise UnsupportedOperationError("cancel not supported")

    @staticmethod
    def _get_cached_answer(uid: str) -> str | None:
        """Return cached answer from scratch/{uid}/answer.txt if it exists."""
        from src.scratch import SCRATCH_ROOT

        answer_file = SCRATCH_ROOT / uid / "answer.txt"
        if answer_file.exists():
            content = answer_file.read_text(encoding="utf-8").strip()
            if content:
                return content.splitlines()[0].strip()
        return None
