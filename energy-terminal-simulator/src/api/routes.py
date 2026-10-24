from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(prefix="/terminals", tags=["terminals"])


class CardRequest(BaseModel):
    cardUid: str


@router.post("/{terminal_id}/card")
async def tap_card(terminal_id: str, body: CardRequest, request: Request):
    manager = request.app.state.manager
    terminal = manager.get_terminal(terminal_id)
    if not terminal:
        raise HTTPException(status_code=404, detail=f"Terminal {terminal_id} not found")
    result = await terminal.present_card(body.cardUid)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result)
    return result


@router.get("")
async def list_terminals(request: Request):
    manager = request.app.state.manager
    return [
        {
            "terminalId": t.terminal_id,
            "state": t.state.value,
            "reservationId": t.reservation_id,
            "sessionId": t.session_id,
        }
        for t in manager.get_all_terminals()
    ]


@router.get("/{terminal_id}")
async def get_terminal(terminal_id: str, request: Request):
    manager = request.app.state.manager
    terminal = manager.get_terminal(terminal_id)
    if not terminal:
        raise HTTPException(status_code=404, detail=f"Terminal {terminal_id} not found")
    return {
        "terminalId": terminal.terminal_id,
        "state": terminal.state.value,
        "reservationId": terminal.reservation_id,
        "sessionId": terminal.session_id,
        "meters": {k: v.reading for k, v in terminal.meters.items()},
    }
