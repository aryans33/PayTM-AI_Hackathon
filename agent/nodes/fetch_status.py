"""
agent/nodes/fetch_status.py
----------------------------
Node 2: fetch_transaction_status (SQLite tool call)

Responsibility: Query the mock SQLite transactions table by transaction_id and
populate transaction_status, amount, payer/payee info in state.

WHAT IS MOCKED: The SQLite query stands in for real NPCI Status API calls and
bank core-banking queries. In production this would be:
    NPCI UPI Status API → GET /v1/transaction/status?txn_id=...
    Bank CBS API        → authenticated REST call to bank's core banking system

WHAT IS REAL: The query logic, error handling, not-found path, and audit
logging are written exactly as they would be in a production system.

Routing (set via "decision" field for graph conditional edges):
    - Transaction found → decision stays None (policy_decision will set it)
    - Transaction not found → decision = "clarify" (ask user to check the ID)
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running from project root or as a module
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agent.state import AgentState
from mock_data.db import get_connection


def fetch_transaction_status(state: AgentState) -> dict:
    """
    LangGraph node: fetch transaction record from the mock SQLite DB.

    Populates: transaction_status, amount (overrides LLM estimate if DB has it),
    payer_vpa, payee_vpa, payee_name, initiated_at.
    """
    transaction_id = state.get("transaction_id")
    trace: list = list(state.get("trace", []))

    trace.append(
        f"[fetch_status] Querying mock transaction database for ID: {transaction_id!r}"
    )

    # ── Safety check ────────────────────────────────────────────────────────
    if not transaction_id:
        # This shouldn't happen if the graph routes correctly, but be defensive.
        trace.append(
            "[fetch_status] WARNING: No transaction_id in state -- graph routing error. "
            "Cannot proceed."
        )
        return {
            "trace": trace,
            "decision": "clarify",
            "response_to_user": (
                "I don't have a transaction ID to look up. "
                "Please provide your UPI transaction reference number."
            ),
        }

    # ── Database query ───────────────────────────────────────────────────────
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT transaction_id, status, amount, currency,
                   payer_vpa, payee_vpa, payee_name, initiated_at,
                   description, bank_ref_number
            FROM   transactions
            WHERE  transaction_id = ?
            """,
            (transaction_id,),
        )
        row = cursor.fetchone()
    finally:
        conn.close()

    # ── Not found ────────────────────────────────────────────────────────────
    if row is None:
        trace.append(
            f"[fetch_status] NOT FOUND: txn={transaction_id!r} -- not in database. "
            f"Possible typo or outside records window."
        )
        return {
            "trace": trace,
            "decision": "clarify",
            "response_to_user": (
                f"I couldn't find transaction {transaction_id} in our records. "
                "Please double-check the transaction ID in your Paytm app's transaction history. "
                "Transaction IDs typically look like TXN_AUTO_001 or similar."
            ),
        }

    # ── Found — populate state ───────────────────────────────────────────────
    status   = row["status"]
    amount   = row["amount"]
    currency = row["currency"]

    trace.append(
        f"[fetch_status] FOUND: txn={transaction_id!r} status={status!r} "
        f"amount=Rs.{amount:,.2f} {currency} payee={row['payee_name']!r}"
    )
    trace.append(
        f"[fetch_status] payer={row['payer_vpa']} payee={row['payee_vpa']} "
        f"bank_ref={row['bank_ref_number']}"
    )

    return {
        "trace":              trace,
        "transaction_status": status,
        "amount":             amount,
        "payer_vpa":          row["payer_vpa"],
        "payee_vpa":          row["payee_vpa"],
        "payee_name":         row["payee_name"],
        "initiated_at":       row["initiated_at"],
        # decision stays None — policy_decision will set it
    }
