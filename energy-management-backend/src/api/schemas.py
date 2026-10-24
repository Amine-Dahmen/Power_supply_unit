import uuid
from datetime import datetime
from typing import List, Optional, Any
from pydantic import BaseModel, ConfigDict, Field


class CreateReservationRequest(BaseModel):
    customer_name: str = Field(..., min_length=1, max_length=100)
    card_uid: str = Field(..., min_length=1, max_length=50)
    requested_services: List[str] = Field(default=["electricity", "water", "gas"])


class ReservationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    customer_name: str
    card_uid: str
    requested_services: List[str]
    status: str
    assigned_terminal_id: Optional[str]
    session_id: Optional[uuid.UUID]
    created_at: datetime
    expires_at: datetime
    updated_at: datetime


class TerminalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: str
    current_session_id: Optional[str]
    updated_at: datetime


class MeterReadingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    meter_type: str
    cumulative_value: float
    unit: str
    is_final: bool
    recorded_at: datetime


class SessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    terminal_id: str
    reservation_id: uuid.UUID
    status: str
    started_at: datetime
    ended_at: Optional[datetime]
    updated_at: datetime


class SessionDetailResponse(SessionResponse):
    readings: List[MeterReadingResponse] = []


class InvoiceLineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    meter_type: str
    consumption: float
    unit: str
    fixed_fee: float
    usage_amount: float
    line_total: float
    tier_breakdown: List[Any] = []


class InvoiceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    total_amount: float
    currency: str
    created_at: datetime
    lines: List[InvoiceLineResponse] = []
