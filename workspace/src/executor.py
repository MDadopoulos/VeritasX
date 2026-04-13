"""
executor.py — A2A AgentExecutor wrapping the existing run_question() pipeline.

Emits Task lifecycle events via TaskUpdater (submitted -> working -> completed)
so the green agent / judge can observe state transitions and consume the
answer as a Task artifact.
"""

from __future__ import annotations

import asyncio
import logging
from uuid import uuid4

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import (
    InvalidRequestError,
    Part,
    TaskState,
    TextPart,
    UnsupportedOperationError,
)
from a2a.utils import new_agent_text_message, new_task
from a2a.utils.errors import ServerError

logger = logging.getLogger(__name__)

TERMINAL_STATES = {
    TaskState.completed,
    TaskState.canceled,
    TaskState.failed,
    TaskState.rejected,
}


class OfficeQAAgentExecutor(AgentExecutor):
    """A2A executor that delegates to run_question() in a thread pool."""

    def __init__(self, max_concurrent: int = 4, timeout: float = 3000.0):
        self._semaphore: asyncio.Semaphore | None = None
        self._max_concurrent = max_concurrent
        self._timeout = timeout

    def _ensure_semaphore(self) -> None:
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self._max_concurrent)

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        from src.agent import run_question

        self._ensure_semaphore()

        msg = context.message
        if not msg:
            raise ServerError(
                error=InvalidRequestError(message="Missing message in request")
            )

        task = context.current_task
        if task and task.status.state in TERMINAL_STATES:
            raise ServerError(
                error=InvalidRequestError(
                    message=f"Task {task.id} already processed "
                            f"(state: {task.status.state})"
                )
            )

        if not task:
            task = new_task(msg)
            await event_queue.enqueue_event(task)

        context_id = task.context_id
        updater = TaskUpdater(event_queue, task.id, context_id)

        question = context.get_user_input()
        if not question:
            await updater.failed(
                new_agent_text_message(
                    "No text content found in A2A message",
                    context_id=context_id,
                    task_id=task.id,
                )
            )
            return

        uid = task.id or str(uuid4())

        # Idempotency: return cached answer without re-running
        cached = self._get_cached_answer(uid)
        if cached is not None:
            logger.info("Returning cached answer for uid=%s", uid)
            await updater.add_artifact(
                [Part(root=TextPart(text=cached))], name="answer"
            )
            await updater.complete()
            return

        await updater.start_work()

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
                await updater.failed(
                    new_agent_text_message(
                        f"Timeout after {self._timeout:.0f}s",
                        context_id=context_id,
                        task_id=task.id,
                    )
                )
                return
            except Exception as e:
                logger.error("Agent crashed for uid=%s", uid, exc_info=True)
                await updater.failed(
                    new_agent_text_message(
                        f"Agent error: {e}",
                        context_id=context_id,
                        task_id=task.id,
                    )
                )
                return

        await updater.add_artifact(
            [Part(root=TextPart(text=answer))], name="answer"
        )
        await updater.complete()

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise ServerError(error=UnsupportedOperationError())

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
