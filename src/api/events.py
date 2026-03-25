import asyncio
import json

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from src.api import deps
from src.auth import decode_jwt

router = APIRouter(tags=["events"])


async def event_generator(user_id: str):
    prefix = f"{user_id}:"
    while True:
        events = deps.manager.collect_events()
        for event in events:
            cid = event.get("connector_id", "")
            if not cid.startswith(prefix):
                continue
            # Strip the user prefix from connector_id for the client
            event = {**event, "connector_id": cid[len(prefix):]}
            event_type = event.get("type", "error")
            if event_type == "status":
                event_type = "worker_status"
            yield {"event": event_type, "data": json.dumps(event)}
        await asyncio.sleep(0.1)


@router.get("/api/events")
async def sse_events(request: Request):
    token = request.cookies.get("mm_session")
    if not token:
        from fastapi import HTTPException
        raise HTTPException(401, "Non authentifié")
    payload = decode_jwt(token, deps.jwt_secret)
    if not payload:
        from fastapi import HTTPException
        raise HTTPException(401, "Session expirée")
    user_id = payload.get("user_id")
    return EventSourceResponse(event_generator(user_id))
