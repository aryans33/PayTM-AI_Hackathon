# UPI Dispute Resolution AI Teammate

Hackathon prototype for **Paytm AI Hackathon — Autonomous AI Teammates track**.

The agent autonomously resolves "debited but not credited" UPI transaction disputes. It checks transaction status, applies a deterministic policy engine, and either auto-refunds, informs the user, or escalates to a human agent — with a **live-streaming decision trace** visible in the UI.

---

## Architecture overview

```
User Message
    │
    ▼
[extract_intent]  ← LLM (Groq / Llama 3.3 70B): parse natural language → structured JSON
    │                  ↑ Pydantic schema validation gate (bad output → clarify)
    ▼
[fetch_status]    ← SQLite query: get transaction status + details
    │
    ▼
[policy_decision] ← PURE DETERMINISTIC PYTHON — NO LLM. if/else policy engine.
    │
    ├─ auto_resolve   → [execute_action] ← idempotent issue_refund()
    ├─ escalate       → [escalate]       ← builds structured handover summary
    ├─ inform_pending  ─────────────────┐
    └─ inform_resolved ─────────────────┤
                                        ▼
                                    [respond]  ← LLM: generate natural-language reply
                                        │
                                        ▼
                                   User sees response
                        + Live trace streamed to right panel
```

### Core safety principle

> **The LLM never makes the refund/escalation decision.**

This is based on real legal precedent: *Moffatt v. Air Canada (2024)*, where the airline was held liable for a chatbot hallucinating a refund policy. `policy_decision.py` is pure Python with zero model involvement. You can verify this: `grep -r "llm_client" agent/nodes/policy_decision.py` returns nothing.

---

## What is mocked vs. production-grade

| Component | Status | Notes |
|---|---|---|
| Bank/NPCI transaction data | **MOCKED** | SQLite stands in for NPCI Status API + bank CBS |
| Refund execution | **MOCKED** | SQLite insert stands in for NPCI UDIR API call |
| MCP server wrapping | **SKIPPED** | Tool functions called directly from LangGraph nodes |
| Agent decision logic | **PRODUCTION-GRADE** | Deterministic, auditable, if/else policy engine |
| Idempotency guard | **PRODUCTION-GRADE** | SQLite ledger, at-most-once refund semantics |
| Schema validation | **PRODUCTION-GRADE** | Pydantic v2 validates all LLM output before use |
| Audit logging | **PRODUCTION-GRADE** | DPDP-style trace, every branch annotated |
| State management | **PRODUCTION-GRADE** | LangGraph MemorySaver, clean TypedDict state |

---

## Setup

### Prerequisites
- Python 3.11+
- Node.js 18+
- A free Groq API key from [console.groq.com](https://console.groq.com) (no credit card)

### 1. Clone / open the project

```bash
cd "d:/CodeKaro/PayTM AI Hackathon"
```

### 2. Set up Python environment

```bash
# Create and activate virtual environment
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS/Linux

# Install dependencies
pip install -r requirements.txt
```

### 3. Configure your API key

```bash
# Copy the example and add your Groq key
copy .env.example .env
# Edit .env and set: GROQ_API_KEY=gsk_...your_key...
```

### 4. Seed the mock database

```bash
python mock_data/seed_data.py
```

This creates `mock_data/upi_disputes.db` with 8 transactions covering all status types.

### 5. Start the API server

```bash
uvicorn api.main:app --reload --port 8000
```

The API will be at `http://localhost:8000`. The database is auto-seeded on startup if empty.

### 6. Start the React frontend (new terminal)

```bash
cd ui
npm run dev
```

Frontend will be at `http://localhost:5173`.

---

## Running tests

```bash
# Activate venv first, then:
python agent/test_agent.py
```

This runs **6 tests** without needing the API server:

| Test | Transaction | Expected decision |
|---|---|---|
| Scenario A | TXN_AUTO_001 (₹300, failed_past_window) | `auto_resolve` |
| Scenario B | TXN_HIGH_001 (₹12,500, failed_past_window) | `escalate` |
| Scenario B alt | TXN_AMB_001 (₹2,100, ambiguous) | `escalate` |
| Scenario C | TXN_FRAUD_001 (₹4,999, fraud_flagged) | `escalate` |
| Missing ID | No transaction ID in message | `clarify` |
| **Idempotency** | Calls `issue_refund()` twice for same ID | 2nd call returns cached result, no duplicate |

---

## Live demo — 3 scenarios

Use the **Demo Scenario Picker** in the UI, or type these messages directly:

### Scenario A — Auto-resolve (routine)
**Transaction:** `TXN_AUTO_001` · ₹300 · `failed_past_window`

**Type:** *"My ₹300 payment to QuickMart failed but money was deducted, transaction ID TXN_AUTO_001"*

**Expected:** Agent auto-resolves, trace shows full reasoning path, user gets refund confirmation.

---

### Scenario B — High-value escalation
**Transaction:** `TXN_HIGH_001` · ₹12,500 · `failed_past_window`

**Type:** *"My flight booking payment of ₹12500 failed, transaction TXN_HIGH_001"*

**Expected:** Agent refuses to act autonomously (amount > ₹5,000 threshold), escalates with clean handover.

Or use `TXN_AMB_001` (ambiguous status) for the same escalation result.

---

### Scenario C — Fraud flagged
**Transaction:** `TXN_FRAUD_001` · ₹4,999 · `fraud_flagged`

**Type:** *"Please refund my transaction TXN_FRAUD_001"*

**Expected:** Immediate escalation, trace explains fraud flag, zero autonomous action taken.

---

## Transaction ID reference

| ID | Status | Amount | Demo path |
|---|---|---|---|
| TXN_OK_001 | success | ₹1,500 | inform_resolved |
| TXN_OK_002 | success | ₹299 | inform_resolved |
| TXN_PEND_001 | failed_pending | ₹800 | inform_pending |
| TXN_PEND_002 | failed_pending | ₹3,200 | inform_pending |
| **TXN_AUTO_001** | failed_past_window | ₹300 | **Scenario A → auto_resolve** |
| **TXN_HIGH_001** | failed_past_window | ₹12,500 | **Scenario B → escalate** |
| **TXN_AMB_001** | ambiguous | ₹2,100 | **Scenario B alt → escalate** |
| **TXN_FRAUD_001** | fraud_flagged | ₹4,999 | **Scenario C → escalate** |

---

## Project structure

```
/agent
  __init__.py
  state.py              ← AgentState TypedDict (single source of truth)
  llm_client.py         ← Groq wrapper (ONLY place LLM is called)
  graph.py              ← LangGraph StateGraph — node wiring + routing
  test_agent.py         ← Standalone test script (no API server needed)
  nodes/
    extract_intent.py   ← Node 1: LLM parse + Pydantic validation
    fetch_status.py     ← Node 2: SQLite query
    policy_decision.py  ← Node 3: PURE DETERMINISTIC PYTHON, NO LLM
    execute_action.py   ← Node 4: Idempotent issue_refund()
    escalate.py         ← Node 5: Structured handover summary
    respond.py          ← Node 6: LLM final response generation

/mock_data
  __init__.py
  db.py                 ← SQLite connection + table schema creation
  seed_data.py          ← Seeds 8 mock transactions (idempotent)
  upi_disputes.db       ← Created automatically on first run

/api
  __init__.py
  main.py               ← FastAPI app: GET /transactions, POST /chat, WS /ws/{thread_id}

/ui
  src/
    App.jsx             ← Root: two-panel layout + WebSocket session management
    App.css             ← Full dark-mode stylesheet
    api.js              ← API/WebSocket helpers
    components/
      ChatPanel.jsx     ← Left panel: chat UI + demo picker
      TracePanel.jsx    ← Right panel: live trace viewer

requirements.txt
.env.example
README.md
```

---

## Policy decision table

Implemented in `agent/nodes/policy_decision.py` — pure Python, verifiable by reading the source:

| Transaction status | Amount | Decision | Reason |
|---|---|---|---|
| `success` | any | `inform_resolved` | Payment went through |
| `failed_pending` | any | `inform_pending` | Within T+1 NPCI auto-reversal window |
| `failed_past_window` | ≤ ₹5,000 | `auto_resolve` | Within autonomous refund threshold |
| `failed_past_window` | > ₹5,000 | `escalate` | Exceeds autonomous action limit |
| `ambiguous` | any | `escalate` | Conflicting data — cannot act safely |
| `fraud_flagged` | any | `escalate` | Suspected fraud — zero autonomous action |
