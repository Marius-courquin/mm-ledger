import asyncio
import json

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from src.api import deps

router = APIRouter(tags=["events"])


async def event_generator():
    while True:
        events = deps.manager.collect_events()
        for event in events:
            event_type = event.get("type", "error")
            if event_type == "status":
                event_type = "worker_status"
            yield {"event": event_type, "data": json.dumps(event)}
        await asyncio.sleep(0.1)


@router.get("/api/events")
async def sse_events():
    return EventSourceResponse(event_generator())
