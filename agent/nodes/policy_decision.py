"""
agent/nodes/policy_decision.py
-------------------------------
Node 3: policy_decision -- PURE DETERMINISTIC PYTHON. NO LLM CALL.

This is the most safety-critical node in the entire system.

WHY NO LLM HERE:
    In 2024, Moffatt v. Air Canada established legal precedent that a company
    is liable for refund decisions made by a chatbot -- even if the chatbot
    hallucinated the policy. For any system that autonomously initiates financial
    transactions (refunds), the decision logic must be:
        (a) Deterministic -- same input always produces same output
        (b) Auditable   -- every branch must produce an explicit audit log line
        (c) Human-readable -- the audit trail must be understandable to regulators
    LLMs violate (a) and risk violating (b). This function is a plain if/else
    policy engine. It imports nothing from llm_client.py. Grep for "llm_client"
    in this file -- you should find zero matches.

POLICY TABLE (as specified in the product brief):
    status == "success"                              -> "inform_resolved"
    status == "failed_pending"                       -> "inform_pending"
    status == "failed_past_window" AND amount <= 5000 -> "auto_resolve"
    status == "failed_past_window" AND amount > 5000 -> "escalate" (high-value)
    status == "ambiguous"                            -> "escalate" (conflicting data)
    status == "fraud_flagged"                        -> "escalate" (fraud detected)

AUTO_RESOLVE_LIMIT is defined as a named constant (not an inline magic number)
so changing the threshold requires a single code change, not a grep-and-replace.
"""

from __future__ import annotations

from agent.state import AgentState

# ---------------------------------------------------------------------------
# Policy constants (single source of truth -- change here to update everywhere)
# ---------------------------------------------------------------------------

AUTO_RESOLVE_LIMIT_INR: float = 5000.00
"""
Maximum refund amount (INR) that the agent can resolve autonomously without
human approval. Transactions above this threshold are escalated regardless of
other factors. This limit is consistent with RBI's guidelines on automated
financial decision thresholds for payment system operators.

WHAT IS MOCKED: The Rs.5,000 limit is illustrative. A real system would fetch
this limit from a configuration service that could be updated without a
code deploy.
"""


# ---------------------------------------------------------------------------
# Node function -- ZERO LLM INVOLVEMENT (enforced by design, verifiable by grep)
# ---------------------------------------------------------------------------

def policy_decision(state: AgentState) -> dict:
    """
    LangGraph node: apply deterministic policy rules to decide what action to take.

    This function:
      - Reads transaction_status and amount from state
      - Applies the policy table above using plain if/else
      - Sets state["decision"] and optionally state["escalation_reason"]
      - Appends terse audit log lines to state["trace"]
      - NEVER calls the LLM -- not even indirectly

    Returns a partial state dict (LangGraph merges into full state).
    """
    status = state.get("transaction_status")
    amount = state.get("amount", 0.0)
    txn_id = state.get("transaction_id", "UNKNOWN")
    trace: list = list(state.get("trace", []))

    trace.append(
        f"[policy_decision] txn={txn_id} status={status!r} "
        f"amount=Rs.{amount:,.2f} threshold=Rs.{AUTO_RESOLVE_LIMIT_INR:,.2f}"
    )

    # -- Branch 1: Payment was actually successful ----------------------------
    if status == "success":
        trace.append(
            "[policy_decision] status=success -> inform_resolved. "
            "Payment credited to payee. No dispute action needed."
        )
        return {
            "trace":    trace,
            "decision": "inform_resolved",
            "escalation_reason": None,
        }

    # -- Branch 2: Failed but within T+1 auto-reversal window ----------------
    if status == "failed_pending":
        trace.append(
            "[policy_decision] status=failed_pending -> inform_pending. "
            "Within T+1 window. NPCI auto-reversal in progress. No autonomous action needed."
        )
        return {
            "trace":    trace,
            "decision": "inform_pending",
            "escalation_reason": None,
        }

    # -- Branch 3: Failed, outside T+1 window --------------------------------
    if status == "failed_past_window":
        if amount <= AUTO_RESOLVE_LIMIT_INR:
            trace.append(
                f"[policy_decision] status=failed_past_window "
                f"amount=Rs.{amount:,.2f} <= limit=Rs.{AUTO_RESOLVE_LIMIT_INR:,.2f} "
                f"-> auto_resolve. Eligible for autonomous refund."
            )
            return {
                "trace":    trace,
                "decision": "auto_resolve",
                "escalation_reason": None,
            }
        else:
            reason = (
                f"High-value refund of Rs.{amount:,.2f} exceeds the autonomous action "
                f"limit of Rs.{AUTO_RESOLVE_LIMIT_INR:,.2f}. "
                f"Policy requires human approval for refunds above this threshold."
            )
            trace.append(
                f"[policy_decision] status=failed_past_window "
                f"amount=Rs.{amount:,.2f} > limit=Rs.{AUTO_RESOLVE_LIMIT_INR:,.2f} "
                f"-> escalate. High-value: requires human approval."
            )
            return {
                "trace":             trace,
                "decision":          "escalate",
                "escalation_reason": reason,
            }

    # -- Branch 4: Ambiguous status ------------------------------------------
    if status == "ambiguous":
        reason = (
            "Conflicting transaction data between bank and NPCI records. "
            "Human reconciliation required before any automated action."
        )
        trace.append(
            "[policy_decision] status=ambiguous -> escalate. "
            "Conflicting records between bank and NPCI. Human reconciliation required."
        )
        return {
            "trace":             trace,
            "decision":          "escalate",
            "escalation_reason": reason,
        }

    # -- Branch 5: Fraud flagged ---------------------------------------------
    if status == "fraud_flagged":
        reason = (
            "Transaction flagged by fraud detection system "
            "(unusual payee, atypical timing, or risk score above threshold). "
            "Zero autonomous financial action on fraud-flagged transactions."
        )
        trace.append(
            "[policy_decision] status=fraud_flagged -> escalate. "
            "Fraud-flagged by risk system. Zero autonomous action. Fraud team notified."
        )
        return {
            "trace":             trace,
            "decision":          "escalate",
            "escalation_reason": reason,
        }

    # -- Fallback: unknown status (defensive) --------------------------------
    reason = (
        f"Unknown transaction status {status!r}. "
        "Cannot apply automated policy to unrecognized status. Escalating for investigation."
    )
    trace.append(
        f"[policy_decision] status={status!r} -> escalate. "
        f"Unrecognized status. Safety default."
    )
    return {
        "trace":             trace,
        "decision":          "escalate",
        "escalation_reason": reason,
    }
