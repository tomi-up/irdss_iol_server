import time
import uuid
import logging
from typing import Dict, List, Optional, Tuple

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Tracks live WebSocket connections per facility and issues short-lived,
    one-time tickets that authorize a connection -- browsers can't attach
    custom headers (RSA signature / X-API-Key) to a native WebSocket
    handshake, so the RSA-authenticated REST layer hands out a ticket instead.
    """

    def __init__(self) -> None:
        self.active_connections: Dict[str, List[WebSocket]] = {}
        self.tickets: Dict[str, Tuple[str, float]] = {}

    def issue_ticket(self, facility_name: str, ttl_seconds: int = 60) -> str:
        token = uuid.uuid4().hex
        self.tickets[token] = (facility_name, time.time() + ttl_seconds)
        return token

    def redeem_ticket(self, token: str) -> Optional[str]:
        """One-time use: the ticket is removed whether or not it's still valid."""
        entry = self.tickets.pop(token, None)
        if not entry:
            return None
        facility_name, expires_at = entry
        if time.time() > expires_at:
            return None
        return facility_name

    async def connect(self, facility_name: str, websocket: WebSocket) -> None:
        await websocket.accept()
        key = facility_name.strip().lower()
        self.active_connections.setdefault(key, []).append(websocket)

    def disconnect(self, facility_name: str, websocket: WebSocket) -> None:
        key = facility_name.strip().lower()
        conns = self.active_connections.get(key)
        if not conns:
            return
        if websocket in conns:
            conns.remove(websocket)
        if not conns:
            self.active_connections.pop(key, None)

    async def broadcast_to_facility(self, facility_name: str, message: dict) -> None:
        """Pushes a JSON message to every open socket for a facility, dropping any that error out."""
        if not facility_name:
            return
        key = facility_name.strip().lower()
        conns = list(self.active_connections.get(key, []))
        if not conns:
            return

        dead: List[WebSocket] = []
        for ws in conns:
            try:
                await ws.send_json(message)
            except Exception as exc:
                logger.warning(f"Dropping dead WebSocket for facility '{facility_name}': {exc}")
                dead.append(ws)

        for ws in dead:
            self.disconnect(facility_name, ws)


manager = ConnectionManager()
