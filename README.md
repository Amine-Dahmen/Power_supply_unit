# Energy Terminal Simulator & Management Backend

Educational IoT & Energy Management System simulating and managing 3 smart energy terminals (`ST-01`, `ST-02`, `ST-03`). Each terminal features independent electricity, water, and gas meters.

The system consists of two strictly decoupled projects communicating solely via an **MQTT 3.1.1** broker:
- **`energy-terminal-simulator`**: Hardware simulator simulating 3 terminals, concurrent state machines, meter generation, and RFID card taps.
- **`energy-management-backend`**: FastAPI REST API, PostgreSQL database with Alembic migrations, session management, live telemetry tracking, and progressive tariff billing.

---

## Architecture Overview

```
                      +-------------------+
                      |   Mosquitto 2.x   |
                      |    (MQTT 1883)    |
                      +---------+---------+
                                |
             +------------------+------------------+
             | (commands / events / telemetry)     |
             v                                     v
+---------------------------+        +---------------------------+
| energy-terminal-simulator |        | energy-management-backend |
|     (FastAPI :8001)       |        |      (FastAPI :8000)      |
+---------------------------+        +-------------+-------------+
             |                                     |
    POST /terminals/{id}/card                      | (SQLAlchemy 2)
     (Simulate RFID Taps)                          v
                                           +---------------+
                                           | PostgreSQL 16 |
                                           +---------------+
```

### Key Principles
1. **Decoupled by Design**: No code or shared packages between simulator and backend. The MQTT JSON message contract is the single source of truth.
2. **Authoritative Sources**:
   - Backend database is the source of truth for reservations, sessions, and billing.
   - Simulator is authoritative for physical meter readings and hardware state.
3. **Idempotency & Double-Billing Prevention**:
   - Every MQTT message carries a unique `messageId` (UUID v4) deduplicated via cache/database.
   - The `invoices` table enforces `UNIQUE(session_id)` to guarantee a session is never billed twice.
4. **No Pre-card Consumption**: Meter generation is strictly prohibited until the assigned card UID is tapped.
5. **Realistic Progressive Pricing**: Tariffs inspired by Tunisian utility pricing (STEG/SONEDE) in Tunisian Dinars (TND) rounded to the millime (3 decimal places).

---

## Tech Stack

- **Language & Runtime**: Python 3.12
- **Backend**: FastAPI, SQLAlchemy 2 (Asyncio), Alembic, asyncpg / psycopg2
- **Simulator**: FastAPI, asyncio state machines, cumulative randomized meters
- **Messaging**: Eclipse Mosquitto, paho-mqtt v2 (MQTT 3.1.1 protocol)
- **Database**: PostgreSQL 16 Alpine
- **Containerization**: Docker & Docker Compose
- **Testing**: pytest, pytest-asyncio, aiosqlite, httpx

---

## Quickstart with Docker Compose

Run the entire ecosystem with one command:

```bash
docker compose up --build
```

### Service Endpoints

| Service | Protocol / Port | Description |
|---|---|---|
| **Backend REST API** | HTTP `http://localhost:8000` | Swagger Docs at [`http://localhost:8000/docs`](http://localhost:8000/docs) |
| **Simulator API** | HTTP `http://localhost:8001` | Card Tap endpoint: `POST http://localhost:8001/terminals/{id}/card` |
| **MQTT Broker** | TCP `localhost:1883` | Eclipse Mosquitto Broker |
| **PostgreSQL** | TCP `localhost:5432` | DB: `borne_energy`, User: `borne`, Pass: `borne_dev` |

---

## Complete End-to-End Workflow

Follow this step-by-step example using `curl` or the Swagger UI:

### 1. Check Initial Terminal States
```bash
curl -X GET http://localhost:8000/terminals
```
All terminals (`ST-01`, `ST-02`, `ST-03`) start in `ACTIVE` state.

### 2. Create a Reservation
Request services (e.g. electricity, water, gas):
```bash
curl -X POST http://localhost:8000/reservations \
  -H "Content-Type: application/json" \
  -d '{
    "customer_name": "Ahmed Ben Ali",
    "card_uid": "RFID-A1B2C3D4",
    "requested_services": ["electricity", "water", "gas"]
  }'
```
Response (201 Created):
```json
{
  "id": "e8387ea6-...",
  "customer_name": "Ahmed Ben Ali",
  "card_uid": "RFID-A1B2C3D4",
  "requested_services": ["electricity", "water", "gas"],
  "status": "ASSIGNED",
  "assigned_terminal_id": "ST-01",
  "session_id": "c71a39f0-...",
  "expires_at": "..."
}
```
*The backend auto-assigns `ST-01`, sets its state to `OCCUPIED`, and sends `ASSIGN_RESERVATION` via MQTT. Terminal `ST-01` enters `WAITING_FOR_CARD`.*

### 3. First RFID Card Tap (Start Consumption)
Tap the matching card UID on `ST-01`:
```bash
curl -X POST http://localhost:8001/terminals/ST-01/card \
  -H "Content-Type: application/json" \
  -d '{"cardUid": "RFID-A1B2C3D4"}'
```
*`ST-01` transitions to `RUNNING` and starts generating cumulative consumption on electricity, water, and gas every 3 seconds.*

*(Optional) Try tapping a wrong card UID `RFID-WRONG`: it will be rejected with HTTP 400 and will not start consumption.*

### 4. Poll Live Consumption
Poll telemetry for the active session:
```bash
curl -X GET http://localhost:8000/sessions/{sessionId}/consumption
```

### 5. Second RFID Card Tap (Stop Session)
Tap the card again to stop the session:
```bash
curl -X POST http://localhost:8001/terminals/ST-01/card \
  -H "Content-Type: application/json" \
  -d '{"cardUid": "RFID-A1B2C3D4"}'
```
*`ST-01` stops meter generation, records final readings, transitions to `STOPPING`, and publishes `FINAL_READINGS` (QoS 1).*

### 6. Automated Backend Billing
The backend receives `FINAL_READINGS`:
- Persists final readings with `is_final = True`.
- Computes billing across tiered brackets.
- Stores invoice with `UNIQUE(session_id)` constraint.
- Sends `COMPLETE_SESSION` command to `ST-01`.
- Terminal resets its meters and returns to `ACTIVE`.

### 7. Retrieve Invoice & Billing Breakdown
```bash
curl -X GET http://localhost:8000/sessions/{sessionId}/invoice
```
Example Output:
```json
{
  "id": "...",
  "session_id": "c71a39f0-...",
  "total_amount": 5.492,
  "currency": "TND",
  "lines": [
    {
      "meter_type": "electricity",
      "consumption": 12.450,
      "unit": "kWh",
      "fixed_fee": 0.500,
      "usage_amount": 2.464,
      "line_total": 2.964,
      "tier_breakdown": [
        {"tier": 1, "range": "0.0-5.0", "applicable": 5.0, "rate": 0.150, "cost": 0.750},
        {"tier": 2, "range": "5.0-20.0", "applicable": 7.450, "rate": 0.230, "cost": 1.714}
      ]
    },
    {
      "meter_type": "water",
      "consumption": 2.380,
      "unit": "m3",
      "fixed_fee": 0.300,
      "usage_amount": 1.003,
      "line_total": 1.303,
      "tier_breakdown": [
        {"tier": 1, "range": "0.0-1.0", "applicable": 1.0, "rate": 0.230, "cost": 0.230},
        {"tier": 2, "range": "1.0-5.0", "applicable": 1.380, "rate": 0.560, "cost": 0.773}
      ]
    },
    {
      "meter_type": "gas",
      "consumption": 18.700,
      "unit": "thermie",
      "fixed_fee": 0.400,
      "usage_amount": 0.825,
      "line_total": 1.225,
      "tier_breakdown": [
        {"tier": 1, "range": "0.0-10.0", "applicable": 10.0, "rate": 0.032, "cost": 0.320},
        {"tier": 2, "range": "10.0-50.0", "applicable": 8.700, "rate": 0.058, "cost": 0.505}
      ]
    }
  ]
}
```

---

## Tariff Brackets (Tunisian Dinar - TND)

| Utility | Tier | Range | Rate (TND / unit) | Fixed Fee (TND) |
|---|---|---|---|---|
| **Electricity** (`kWh`) | Tier 1 | 0 – 5 | 0.150 | 0.500 |
| | Tier 2 | 5 – 20 | 0.230 | — |
| | Tier 3 | > 20 | 0.350 | — |
| **Water** (`m³`) | Tier 1 | 0 – 1 | 0.230 | 0.300 |
| | Tier 2 | 1 – 5 | 0.560 | — |
| | Tier 3 | > 5 | 1.130 | — |
| **Gas** (`thermie`) | Tier 1 | 0 – 10 | 0.032 | 0.400 |
| | Tier 2 | 10 – 50 | 0.058 | — |
| | Tier 3 | > 50 | 0.098 | — |

---

## MQTT Topic Contract

| Topic | Publisher | Subscriber | QoS | Retain | Description |
|---|---|---|---|---|---|
| `energy/terminals/{id}/commands` | Backend | Simulator | 1 | No | Commands (`ASSIGN_RESERVATION`, `COMPLETE_SESSION`) |
| `energy/terminals/{id}/events` | Simulator | Backend | 1 | No | Events (`COMMAND_ACK`, `SESSION_STARTED`, `FINAL_READINGS`, `CARD_REJECTED`, `RESERVATION_EXPIRED`, `STATE_CHANGED`, `ERROR`, `ERROR_CLEARED`) |
| `energy/terminals/{id}/telemetry` | Simulator | Backend | 0 | No | Periodic cumulative meter readings |
| `energy/terminals/{id}/status` | Simulator | All | 1 | Yes | Retained terminal hardware state & LWT offline |
| `energy/simulator/status` | Simulator | Backend | 1 | Yes | Simulator process health & LWT |

---

## Test Suite Execution

Both projects have comprehensive automated test suites using `pytest`:

### 1. Run Simulator Tests (21 tests)
```bash
python -m pytest energy-terminal-simulator/tests -v
```
- State machine transitions & guards (`ACTIVE` -> `WAITING_FOR_CARD` -> `RUNNING` -> `STOPPING` -> `COMPLETED` -> `ACTIVE`).
- Meter cumulative tick generation, resets, and random seed determinism.
- RFID card tap validation (matching card tap, wrong card tap rejection).
- Reservation timeout auto-expiry.
- MQTT handlers and command deduplication.

### 2. Run Backend Tests (18 tests)
```bash
python -m pytest energy-management-backend/tests -v
```
- Progressive tier billing calculation across single, multi-tier, zero-consumption, boundary, and multi-meter sessions.
- Idempotent invoice storage and double-billing prevention via DB unique constraint.
- Terminal allocation & concurrency (`409 Conflict` when terminals exhausted).
- Session lifecycle and live telemetry upserts.
- MQTT event dispatching and idempotency filtering.

**Total Test Count: 39 tests passing (100% pass rate).**
