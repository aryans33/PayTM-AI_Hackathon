"""
agent/nodes/respond.py
-----------------------
Node 6 (final): respond — generate a natural-language response for the user.

This is the SECOND and last place where the LLM is called (the first is
extract_intent). The LLM here is used purely as a language generation layer --
it reads the decision that was already made by the deterministic policy engine
and writes it as a clear, direct message to the customer.

The LLM cannot change or override the decision. It receives:
    - The final decision (e.g., "auto_resolve", "escalate")
    - The escalation reason (if applicable)
    - Transaction details
    - A summary of what happened

Its only job is to render that information in natural language.
"""

from __future__ import annotations

from agent.state import AgentState
from agent.llm_client import invoke

# ---------------------------------------------------------------------------
# System prompt -- language generation ONLY, decision already made
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """You are a UPI dispute resolution assistant. Write a short, direct chat message to the customer about their dispute outcome.

RULES (strictly enforced):
- Maximum 3 sentences. Never more than 4.
- No greetings, no sign-offs (no "Hi", "Dear", "Best regards", "Customer Support Team").
- No empathy filler ("I understand how stressful", "I know this can be frustrating").
- No emoji, no decorative symbols, no bullet points.
- State facts directly: what happened, what action was taken, what the customer should expect.
- Use Rs. instead of the rupee symbol in responses.
- Do NOT mention AI, LLM, or internal system names.
- Do NOT make any promises not supported by the context.
"""


def _build_context_prompt(state: AgentState) -> str:
    """Build the user-role prompt describing what the agent decided and why."""
    decision          = state.get("decision")
    amount            = state.get("amount", 0.0)
    txn_id            = state.get("transaction_id", "your transaction")
    payee_name        = state.get("payee_name", "the merchant")
    escalation_reason = state.get("escalation_reason")

    if decision == "auto_resolve":
        return (
            f"The customer reported a 'debited but not credited' issue. "
            f"Transaction ID: {txn_id}, Amount: Rs.{amount:,.2f}, Payee: {payee_name}. "
            f"The transaction failed outside the auto-reversal window but the amount "
            f"is within our autonomous refund limit. "
            f"The system has ALREADY initiated a refund of Rs.{amount:,.2f}. "
            f"Tell the customer: refund initiated, will reflect in 5-7 business days, "
            f"no further action needed from their side."
        )

    if decision == "inform_pending":
        return (
            f"Transaction ID: {txn_id}, Amount: Rs.{amount:,.2f}, Payee: {payee_name}. "
            f"The transaction failed but it is within the 24-hour auto-reversal window. "
            f"NPCI's automatic reversal system is already processing the refund. "
            f"Tell the customer their money will be refunded automatically within 24-48 hours "
            f"and no action is needed on their part."
        )

    if decision == "inform_resolved":
        return (
            f"Transaction ID: {txn_id}, Amount: Rs.{amount:,.2f}, Payee: {payee_name}. "
            f"The transaction actually SUCCEEDED -- payment went through. "
            f"Tell the customer the payment was completed successfully and to check "
            f"their transaction history or contact the payee if they didn't receive it."
        )

    if decision == "escalate":
        return (
            f"Transaction ID: {txn_id}, Amount: Rs.{amount:,.2f}, Payee: {payee_name}. "
            f"This case has been escalated to a human support agent because: {escalation_reason}. "
            f"The system did NOT take any financial action. "
            f"Tell the customer their case has been escalated to the support team, "
            f"give them a reassuring ETA (24-48 hours for complex cases), "
            f"and let them know they don't need to re-explain anything -- "
            f"all details have been passed to the human agent."
        )

    if decision == "clarify":
        return (
            "The customer's message was missing required information (transaction ID). "
            "Politely ask them to provide their UPI transaction ID, "
            "explaining where they can find it (Paytm app -> Transaction History)."
        )

    # Fallback
    return (
        f"Transaction ID: {txn_id}. Something unexpected occurred. "
        "Apologize and ask the customer to contact support directly."
    )


def respond(state: AgentState) -> dict:
    """
    LangGraph node: generate the final natural-language response to the user.

    If a response was already set by a previous node (e.g., clarification from
    extract_intent), skip the LLM call and use it directly -- avoid an unnecessary
    round-trip.
    """
    trace: list = list(state.get("trace", []))
    decision    = state.get("decision")

    # If a prior node already set a specific response (e.g., clarification),
    # use it directly instead of sending to LLM.
    existing_response = state.get("response_to_user")
    if decision == "clarify" and existing_response:
        trace.append(
            f"[respond] decision='clarify' -- using pre-set clarification response "
            f"(no LLM call needed)."
        )
        return {"trace": trace, "response_to_user": existing_response}

    trace.append(
        f"[respond] ---"
    )
    trace.append(
        f"[respond] Generating customer-facing response for decision={decision!r} "
        f"via LLM (language generation only -- decision already made by policy engine)."
    )

    context_prompt = _build_context_prompt(state)

    try:
        response_text = invoke(
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=context_prompt,
            temperature=0.4,    # Slightly higher for natural-sounding language
            max_tokens=200,     # Capped lower to enforce brevity
        )
    except RuntimeError as exc:
        trace.append(f"[respond] LLM call failed: {exc}. Using fallback template.")
        response_text = _fallback_response(state)

    trace.append(f"[respond] Customer response generated.")

    return {
        "trace":            trace,
        "response_to_user": response_text,
    }


def _fallback_response(state: AgentState) -> str:
    """Deterministic fallback in case the LLM is unavailable."""
    decision = state.get("decision")
    txn_id   = state.get("transaction_id", "your transaction")
    amount   = state.get("amount", 0.0)

    if decision == "auto_resolve":
        return (
            f"Refund of Rs.{amount:,.2f} for {txn_id} has been initiated. "
            f"The amount will be credited to your account within 5-7 business days."
        )
    if decision == "inform_pending":
        return (
            f"Your {txn_id} failed but an automatic NPCI reversal is already in progress. "
            f"Rs.{amount:,.2f} will be refunded within 24-48 hours -- no action needed."
        )
    if decision == "inform_resolved":
        return (
            f"Transaction {txn_id} completed successfully on our end. "
            f"Check your transaction history or contact the payee if you haven't received it."
        )
    if decision == "escalate":
        return (
            f"Your case ({txn_id}) has been escalated to our support team. "
            f"You'll hear back within 24-48 hours -- no further action needed from you."
        )
    return (
        "Unable to process your request at this time. "
        "Please contact Paytm support for assistance."
    )
