"""
agent/state.py
--------------
AgentState TypedDict — the single source of truth for all data flowing through
the LangGraph graph.

Every node receives the full state dict and returns a partial dict with only
the fields it mutates. LangGraph merges the partial dict back into state
automatically.

Field notes
-----------
transaction_status:
    Canonical values consumed by policy_decision (pure Python, no LLM):
    - "success"            → payment completed, inform user
    - "failed_pending"     → within T+1 reversal window, inform pending
    - "failed_past_window" → outside window, eligible for auto-resolve or escalate
    - "ambiguous"          → conflicting data, must escalate
    - "fraud_flagged"      → fraud detected, must escalate

decision:
    Set by policy_decision node (never by an LLM):
    - "auto_resolve"      → issue refund autonomously
    - "escalate"          → hand off to human agent
    - "inform_pending"    → tell user reversal is already in progress
    - "inform_resolved"   → tell user payment actually succeeded
    - "clarify"           → ask user for missing/malformed details

trace:
    List of human-readable audit log lines appended by every node.
    Streamed live to the frontend via WebSocket.
    Framed as a DPDP-compliant audit trail for automated financial decisions.
"""

from typing import TypedDict, Optional


class AgentState(TypedDict):
    # --- Input ---
    user_message: str                   # Raw user input

    # --- Extracted by extract_intent (LLM + Pydantic validation) ---
    transaction_id: Optional[str]       # e.g. "TXN_AUTO_001"
    amount: Optional[float]             # Amount in INR, from user message or DB
    complaint_type: Optional[str]       # e.g. "debited_not_credited"

    # --- Populated by fetch_transaction_status (SQLite query) ---
    transaction_status: Optional[str]   # One of the 5 canonical status values above
    payer_vpa: Optional[str]
    payee_vpa: Optional[str]
    payee_name: Optional[str]
    initiated_at: Optional[str]         # ISO-8601 timestamp

    # --- Set by policy_decision (pure deterministic Python — NO LLM) ---
    decision: Optional[str]             # One of the 5 decision values above
    escalation_reason: Optional[str]    # Human-readable reason if decision == "escalate"

    # --- Set by escalate node ---
    handover_summary: Optional[str]     # Structured summary for human agent

    # --- Set by respond node (LLM call) ---
    response_to_user: Optional[str]     # Final natural-language message to user

    # --- Audit trail — appended by every node, streamed live to UI ---
    trace: list                         # list[str] — DPDP-style decision audit log
