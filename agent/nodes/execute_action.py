"""
agent/nodes/execute_action.py
------------------------------
Node 4: execute_action -- issue_refund with idempotency guarantee.

Responsibility: When policy_decision sets decision="auto_resolve", this node
calls issue_refund(). The refund execution is fully idempotent:

    IDEMPOTENCY CONTRACT:
    If issue_refund(transaction_id, amount) is called more than once for the
    same transaction_id, ONLY the first call executes the refund. All subsequent
    calls return the cached result of the first call WITHOUT executing a second
    refund. This is enforced via the processed_refunds SQLite table (effectively
    an idempotency ledger).

    This matches how production payment systems handle idempotency:
    Stripe uses idempotency keys, NPCI uses transaction IDs. The key property
    is that the side-effect (money movement) is triggered at most once, even
    if the calling code retries due to network errors or LangGraph replays.

WHAT IS MOCKED: In production, issue_refund would call:
    - NPCI's UDIR (Unified Dispute and Issue Resolution) API to raise a dispute
    - The acquiring bank's refund API to initiate the credit back to the payer
    The SQLite insert here represents those API calls completing successfully.

WHAT IS REAL: The idempotency logic, ledger structure, and audit logging are
written to exactly the standard a production payment system would require.
"""

from __future__ import annotations

from datetime import datetime, timezone

from agent.state import AgentState
from mock_data.db import get_connection


def _issue_refund(transaction_id: str, amount: float) -> dict:
    """
    Core refund tool function (called by the execute_action node).

    This is a standalone, testable function -- not a LangGraph node. It is
    separated so test_agent.py can call it directly to verify idempotency
    without running the full graph.

    Returns
    -------
    dict with keys:
        success          : bool -- True if refund was processed or already cached
        already_processed: bool -- True if this was a duplicate call (cached result)
        refund_timestamp : str  -- ISO-8601 UTC timestamp of when the refund was
                                   first processed
        amount           : float
        transaction_id   : str
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()

        # -- Idempotency check ------------------------------------------------
        # Check the processed_refunds ledger BEFORE executing any action.
        cursor.execute(
            "SELECT refund_timestamp, amount FROM processed_refunds WHERE transaction_id = ?",
            (transaction_id,),
        )
        existing = cursor.fetchone()

        if existing is not None:
            # -- DUPLICATE CALL -- return cached result, take NO new action ---
            return {
                "success":           True,
                "already_processed": True,
                "refund_timestamp":  existing["refund_timestamp"],
                "amount":            existing["amount"],
                "transaction_id":    transaction_id,
            }

        # -- FIRST CALL -- execute the refund ---------------------------------
        # In production: call bank refund API + NPCI UDIR API here.
        # Here: insert into the idempotency ledger to record the action.
        refund_timestamp = datetime.now(timezone.utc).isoformat()

        cursor.execute(
            """
            INSERT INTO processed_refunds (transaction_id, refund_timestamp, amount, idempotency_key)
            VALUES (?, ?, ?, ?)
            """,
            (transaction_id, refund_timestamp, amount, transaction_id),
        )
        conn.commit()

        return {
            "success":           True,
            "already_processed": False,
            "refund_timestamp":  refund_timestamp,
            "amount":            amount,
            "transaction_id":    transaction_id,
        }

    finally:
        conn.close()


def execute_action(state: AgentState) -> dict:
    """
    LangGraph node: execute the auto-resolve action (issue refund).

    Only runs when policy_decision sets decision="auto_resolve".
    The LangGraph graph conditional edge routes here; all other decisions
    skip this node entirely.
    """
    transaction_id = state.get("transaction_id")
    amount         = state.get("amount", 0.0)
    trace: list    = list(state.get("trace", []))

    trace.append(
        f"[execute_action] Initiating refund for txn={transaction_id} "
        f"amount=Rs.{amount:,.2f} idempotency_key={transaction_id!r}"
    )
    trace.append(
        "[execute_action] Checking processed_refunds ledger for prior execution..."
    )

    result = _issue_refund(transaction_id, amount)

    if result["already_processed"]:
        # -- Duplicate call -- idempotency protection fired -------------------
        trace.append(
            f"[execute_action] IDEMPOTENCY: Refund already processed for {transaction_id} "
            f"at {result['refund_timestamp']}. "
            f"Returning cached result -- no duplicate refund executed."
        )
    else:
        # -- First execution --------------------------------------------------
        trace.append(
            f"[execute_action] REFUND EXECUTED: Rs.{result['amount']:,.2f} refund "
            f"initiated for {transaction_id}. "
            f"Timestamp: {result['refund_timestamp']}. Idempotency ledger updated."
        )
        trace.append(
            "[execute_action] [MOCK] In production: NPCI UDIR dispute raised + "
            "bank refund API called. Funds credited within 5-7 business days."
        )

    return {
        "trace": trace,
    }
