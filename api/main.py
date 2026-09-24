"""
api/main.py
-----------
FastAPI application — REST + WebSocket endpoints for the UPI Dispute Resolution
AI agent.

Endpoints:
    GET  /transactions      — returns all seeded transactions (for demo picker UI)
    POST /chat              — synchronous chat (fallback, no streaming)
    WS   /ws/{thread_id}    — WebSocket: streams trace lines live as agent runs

WebSocket protocol:
    Client sends: JSON  { "message": "<user text>" }
    Server sends: JSON messages in this sequence:
        { "type": "trace",    "content": "<trace line>" }   ← repeated per line
        { "type": "response", "content": "<agent reply>" }
        { "type": "done",     "decision": "<decision>",
          "handover_summary": "<str or null>" }
        { "type": "error",    "content": "<error message>" } ← on failure

The WebSocket handler uses asyncio.Queue to bridge the synchronous LangGraph
stream with the async WebSocket send. Each trace line is pushed to the queue
by the trace_callback, and the WebSocket drains it concurrently.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Allow running from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from mock_data.db import get_connection
from mock_data.seed_data import seed as seed_db
from agent.graph import run_agent

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="UPI Dispute Resolution AI Agent API",
    description=(
        "Backend API for the UPI Dispute Resolution AI Teammate. "
        "Handles chat requests and streams live decision traces via WebSocket."
    ),
    version="1.0.0",
)

# Allow the Vite dev server (localhost:5173) and any origin during hackathon demo
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Startup: seed the mock DB if not already populated
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup_event():
    """Auto-seed the mock DB on startup if it's empty."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM transactions")
        count = cursor.fetchone()["cnt"]
    finally:
        conn.close()

    if count == 0:
        print("[startup] Mock DB is empty — seeding...")
        seed_db()
    else:
        print(f"[startup] Mock DB has {count} transactions — skipping seed.")


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------

@app.get("/transactions")
async def list_transactions():
    """
    Return all mock transactions for the demo picker UI.
    Frontend uses this to populate the transaction ID dropdown.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT transaction_id, status, amount, currency,
                   payer_vpa, payee_vpa, payee_name, initiated_at, description
            FROM   transactions
            ORDER  BY initiated_at DESC
            """
        )
        rows = cursor.fetchall()
        return {
            "transactions": [dict(row) for row in rows]
        }
    finally:
        conn.close()


class ChatRequest(BaseModel):
    message: str
    thread_id: str | None = None


@app.post("/chat")
async def chat_sync(req: ChatRequest):
    """
    Synchronous chat endpoint (no streaming).
    Useful for debugging or as a fallback if WebSocket isn't available.
    """
    thread_id = req.thread_id or str(uuid.uuid4())
    result = await run_agent(req.message, thread_id)
    return {
        "thread_id":       thread_id,
        "response":        result["response_to_user"],
        "decision":        result["decision"],
        "trace":           result["trace"],
        "handover_summary": result.get("handover_summary"),
    }


# ---------------------------------------------------------------------------
# WebSocket endpoint — live trace streaming
# ---------------------------------------------------------------------------

@app.websocket("/ws/{thread_id}")
async def websocket_endpoint(websocket: WebSocket, thread_id: str):
    """
    WebSocket handler for streaming the agent's decision trace in real time.

    Flow:
        1. Client connects, server accepts.
        2. Client sends { "message": "..." }
        3. Server runs the LangGraph agent with a trace_callback that pushes
           each trace line to an asyncio.Queue.
        4. A producer coroutine drains the queue and sends each line to the
           client as { "type": "trace", "content": "..." }
        5. When the agent finishes, server sends the final response and "done".
        6. The connection stays open for subsequent messages (multi-turn).
    """
    await websocket.accept()
    print(f"[ws] Client connected — thread_id={thread_id}")

    try:
        while True:
            # ── Wait for client message ───────────────────────────────────
            raw = await websocket.receive_text()
            try:
                payload = json.loads(raw)
                user_message = payload.get("message", "").strip()
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type":    "error",
                    "content": "Invalid JSON payload — expected {\"message\": \"...\"}",
                })
                continue

            if not user_message:
                await websocket.send_json({
                    "type":    "error",
                    "content": "Empty message received.",
                })
                continue

            # ── Set up trace streaming via asyncio.Queue ──────────────────
            trace_queue: asyncio.Queue[str | None] = asyncio.Queue()

            async def trace_callback(line: str) -> None:
                """Called by run_agent for each new trace line."""
                await trace_queue.put(line)

            # ── Run agent + stream trace concurrently ─────────────────────
            # We run the agent as a task and drain the trace queue in parallel.
            agent_task = asyncio.create_task(
                run_agent(user_message, thread_id, trace_callback)
            )

            # Drain trace queue until agent finishes
            while not agent_task.done() or not trace_queue.empty():
                try:
                    line = await asyncio.wait_for(trace_queue.get(), timeout=0.1)
                    await websocket.send_json({
                        "type":    "trace",
                        "content": line,
                    })
                except asyncio.TimeoutError:
                    # Agent still running, no new trace line — just loop
                    continue

            # ── Agent done — get final result ─────────────────────────────
            try:
                result = await agent_task
            except Exception as exc:
                await websocket.send_json({
                    "type":    "error",
                    "content": f"Agent error: {str(exc)}",
                })
                continue

            # Send final response
            await websocket.send_json({
                "type":    "response",
                "content": result.get("response_to_user", ""),
            })

            # Send done signal with metadata
            await websocket.send_json({
                "type":             "done",
                "decision":         result.get("decision", ""),
                "transaction_id":   result.get("transaction_id"),
                "amount":           result.get("amount"),
                "handover_summary": result.get("handover_summary"),
            })

    except WebSocketDisconnect:
        print(f"[ws] Client disconnected — thread_id={thread_id}")
    except Exception as exc:
        print(f"[ws] Unexpected error — thread_id={thread_id}: {exc}")
        try:
            await websocket.send_json({
                "type":    "error",
                "content": f"Internal server error: {str(exc)}",
            })
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok", "service": "UPI Dispute Resolution AI Agent"}


# ---------------------------------------------------------------------------
# Dev runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
