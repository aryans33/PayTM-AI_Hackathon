"""
agent/nodes/escalate.py
------------------------
Node 5: escalate — build a structured handover summary for a human agent.

This node runs when policy_decision sets decision="escalate".

Responsibility: Compile all available state into a structured handover document
that a human support agent can act on immediately, without needing the customer
to repeat any information. This is a key operational requirement for escalation
workflows — every piece of context must be captured at the point of handoff.

No LLM is used here. The summary is built deterministically from state fields.
This is intentional: the handover must be reliable even if the LLM is unavailable.
"""

from __future__ import annotations

from datetime import datetime, timezone

from agent.state import AgentState


def escalate(state: AgentState) -> dict:
    """
    LangGraph node: build a structured human-agent handover summary.
    """
    trace: list = list(state.get("trace", []))

    txn_id            = state.get("transaction_id", "UNKNOWN")
    status            = state.get("transaction_status", "UNKNOWN")
    amount            = state.get("amount", 0.0)
    payer_vpa         = state.get("payer_vpa", "N/A")
    payee_vpa         = state.get("payee_vpa", "N/A")
    payee_name        = state.get("payee_name", "N/A")
    initiated_at      = state.get("initiated_at", "N/A")
    escalation_reason = state.get("escalation_reason", "Not specified")
    complaint_type    = state.get("complaint_type", "N/A")
    escalated_at      = datetime.now(timezone.utc).isoformat()

    # Build the full trace as a readable block for the handover doc
    trace_text = "\n".join(
        f"    {i+1:02d}. {line}" for i, line in enumerate(trace)
    )

    handover_summary = f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║          UPI DISPUTE — HUMAN AGENT HANDOVER SUMMARY                        ║
╚══════════════════════════════════════════════════════════════════════════════╝

ESCALATED AT : {escalated_at}
ESCALATED BY : UPI Dispute Resolution AI Agent (Autonomous System)

── TRANSACTION DETAILS ────────────────────────────────────────────────────────
  Transaction ID   : {txn_id}
  Status           : {status}
  Amount           : ₹{amount:,.2f} INR
  Initiated At     : {initiated_at}
  Payer VPA        : {payer_vpa}
  Payee VPA        : {payee_vpa}
  Payee Name       : {payee_name}
  Complaint Type   : {complaint_type}

── REASON FOR ESCALATION ──────────────────────────────────────────────────────
  {escalation_reason}

── WHAT THE AI AGENT HAS DONE ─────────────────────────────────────────────────
  • Queried mock transaction database and retrieved current status
  • Applied deterministic policy rules — autonomous resolution is NOT appropriate
  • NO refund or financial action has been taken by the AI agent
  • Full decision trace is provided below for audit purposes

── WHAT THE HUMAN AGENT SHOULD DO ─────────────────────────────────────────────
  1. Review the transaction details above
  2. Contact the payer's bank ({payer_vpa.split('@')[-1] if '@' in (payer_vpa or '') else 'N/A'}) for status reconciliation
  3. If fraud is suspected, flag for the fraud investigation team before any refund
  4. For high-value refunds: obtain supervisor approval before processing
  5. Update the customer via their registered contact with resolution ETA

── AI DECISION TRACE (DPDP Audit Log) ─────────────────────────────────────────
{trace_text}

── END OF HANDOVER SUMMARY ────────────────────────────────────────────────────
""".strip()

    trace.append(
        f"[escalate] ESCALATED: txn={txn_id} handed over to human support team."
    )
    trace.append(
        "[escalate] Structured handover summary generated with full transaction context."
    )
    trace.append(
        "[escalate] No financial action was taken by the AI system. Human agent handles next steps."
    )

    return {
        "trace":            trace,
        "handover_summary": handover_summary,
    }