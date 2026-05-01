"""Lightweight server-sent-event plumbing.

The pipeline scatters `emit()` calls at stage boundaries; the streaming
endpoint owns an `EventEmitter` and consumes its queue as SSE. Threading is
avoided via a contextvar — set the emitter once at request entry, every
nested coroutine sees it for free.
"""

import asyncio
import json
import time
from contextvars import ContextVar
from typing import Any, AsyncIterator, Optional

_emitter: ContextVar[Optional["EventEmitter"]] = ContextVar("event_emitter", default=None)


class EventEmitter:
    def __init__(self) -> None:
        self.queue: asyncio.Queue = asyncio.Queue()
        self._t0 = time.time()

    async def stage(self, verb: str, **extra: Any) -> None:
        await self.queue.put({
            "type": "stage",
            "verb": verb,
            "elapsed_ms": int((time.time() - self._t0) * 1000),
            **extra,
        })

    async def result(self, data: Any) -> None:
        await self.queue.put({"type": "result", "data": data})

    async def error(self, message: str) -> None:
        await self.queue.put({"type": "error", "message": message})

    async def close(self) -> None:
        await self.queue.put(None)

    async def stream(self) -> AsyncIterator[str]:
        while True:
            evt = await self.queue.get()
            if evt is None:
                return
            yield f"data: {json.dumps(evt)}\n\n"


async def emit(verb: str, **extra: Any) -> None:
    """Fire-and-forget stage event. No-op if no emitter is bound to the context."""
    em = _emitter.get()
    if em is not None:
        await em.stage(verb, **extra)


def bind_emitter(em: EventEmitter):
    """Install `em` as the current context's emitter; returns the contextvar token."""
    return _emitter.set(em)


def reset_emitter(token) -> None:
    _emitter.reset(token)
