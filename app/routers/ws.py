from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from app.utils.ws_manager import manager

router = APIRouter()


@router.websocket("/ws/referrals")
async def referral_updates_ws(websocket: WebSocket, ticket: str = Query(...)):
    """
    Real-time push channel for referral lifecycle events (new referral, seen,
    accepted, redirected, finalized, not-selected, cancelled, arrived).
    Authorized by a one-time ticket obtained from POST /api/v1/ws-ticket,
    since native browser WebSockets can't carry the RSA signature headers.
    """
    facility_name = manager.redeem_ticket(ticket)
    if not facility_name:
        await websocket.close(code=4401)
        return

    await manager.connect(facility_name, websocket)
    try:
        while True:
            # Connection is server-push only; any client message is just a keepalive ping.
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(facility_name, websocket)
