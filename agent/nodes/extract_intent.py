"""
agent/nodes/extract_intent.py
------------------------------
Node 1: extract_intent (LLM call + strict schema validation)

Responsibility: Parse the user's natural-language message into a structured
dict containing transaction_id, amount, and complaint_type.

LLM is used ONLY here for NLU/parsing. It has no decision-making authority.

Critical safety layer: The LLM output is validated against a strict Pydantic
schema before any field is used downstream. If validation fails (missing fields,
wrong types, LLM hallucination, parse error), the node sets decision="clarify"
and asks the user a follow-up question. It NEVER passes bad data to fetch_status
or policy_decision.

Routing:
    - If extraction succeeds + transaction_id present → "fetch_status"
    - If extraction fails or transaction_id missing → "clarify" (handled in graph.py)
"""

from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, field_validator, ValidationError

from agent.state import AgentState
from agent.llm_client import invoke_json

# ---------------------------------------------------------------------------
# Pydantic schema — the LLM must produce data that satisfies this model.
# ---------------------------------------------------------------------------

class ExtractedIntent(BaseModel):
    """
    Structured intent extracted from the user's message.

    All fields are Optional because the LLM may not find them in the input.
    The node checks required fields after validation and routes to clarification
    if they're absent.
    """
    transaction_id: Optional[str] = None
    amount: Optional[float] = None
    complaint_type: Optional[str] = None  # e.g. "debited_not_credited", "general_inquiry"

    @field_validator("transaction_id", mode="before")
    @classmethod
    def clean_transaction_id(cls, v):
        """Strip whitespace and normalize case. Reject obviously invalid values."""
        if v is None:
            return None
        cleaned = str(v).strip().upper()
        # Transaction IDs in our mock DB are 3–20 alphanumeric chars + underscores.
        if not re.match(r"^[A-Z0-9_]{3,30}$", cleaned):
            return None   # Treat malformed ID as absent → route to clarification
        return cleaned

    @field_validator("amount", mode="before")
    @classmethod
    def coerce_amount(cls, v):
        """Accept strings like '₹300', '300.00', '1,500' and coerce to float."""
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return float(v)
        # Strip currency symbols and commas, then parse.
        cleaned = re.sub(r"[₹,\s]", "", str(v))
        try:
            return float(cleaned)
        except ValueError:
            return None


# ---------------------------------------------------------------------------
# System prompt for the LLM (intent extraction only — no policy reasoning)
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """You are a UPI transaction dispute intake assistant.
Your ONLY job is to extract structured information from the user's message.
You must NOT reason about what should be done, make recommendations, or express opinions.

Extract the following fields from the user's message:
- transaction_id: The UPI transaction reference ID (often starts with TXN or similar).
  If the user mentions something like "transaction ID TXN_AUTO_001" or "ref TXN123", extract it.
  Return null if not mentioned.
- amount: The transaction amount in INR. Return as a plain number (no currency symbols).
  Return null if not mentioned.
- complaint_type: Classify as one of:
    "debited_not_credited" — money deducted from payer but not received by payee
    "double_debit"         — money deducted twice
    "general_inquiry"      — user asking about status without clear complaint
    "other"                — anything else

Return ONLY a JSON object with exactly these keys: transaction_id, amount, complaint_type.
"""


# ---------------------------------------------------------------------------
# Node function
# ---------------------------------------------------------------------------

def extract_intent(state: AgentState) -> dict:
    """
    LangGraph node: extract structured intent from the user's message.

    Returns a partial state dict. If extraction fails or transaction_id is
    missing, sets decision="clarify" so the graph routes to the respond node
    which will ask the user for the missing information.
    """
    user_message = state["user_message"]
    trace: list = list(state.get("trace", []))

    trace.append(
        f"[extract_intent] Received user message: '{user_message[:120]}{'...' if len(user_message) > 120 else ''}'"
    )
    trace.append("[extract_intent] Calling LLM (Groq / Llama 3.3 70B) to parse intent from natural language...")

    # ── Step 1: LLM call ────────────────────────────────────────────────────
    llm_failed = False
    raw_dict = {"transaction_id": None, "amount": None, "complaint_type": "debited_not_credited"}
    try:
        raw_dict = invoke_json(
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=user_message,
        )
    except RuntimeError as exc:
        # LLM unavailable (e.g. model removed, rate limit, API down).
        # Do NOT immediately return "clarify" — the regex fallback in Step 4
        # will still extract the transaction_id from the raw message text.
        llm_failed = True
        trace.append(
            f"[extract_intent] LLM call failed: {str(exc)[:200]}. "
            f"Falling back to regex extraction on raw message."
        )

    # ── Step 2: Detect LLM parse error (from invoke_json) ───────────────────
    if not llm_failed and "error" in raw_dict and raw_dict["error"] == "parse_failed":
        trace.append(
            f"[extract_intent] LLM returned malformed JSON: "
            f"'{raw_dict.get('raw_output', '')[:200]}'. Will try regex fallback."
        )
        # Fall through — treat as if LLM returned null transaction_id
        raw_dict = {"transaction_id": None, "amount": None, "complaint_type": "debited_not_credited"}

    # ── Step 3: Pydantic schema validation ──────────────────────────────────
    try:
        intent = ExtractedIntent(**raw_dict)
    except (ValidationError, TypeError):
        # Fall through to regex — don't immediately clarify
        trace.append(
            "[extract_intent] Pydantic validation failed on LLM output. Will try regex fallback."
        )
        intent = ExtractedIntent(transaction_id=None, amount=None, complaint_type="debited_not_credited")

    trace.append(
        f"[extract_intent] Intent extracted successfully — "
        f"transaction_id={intent.transaction_id!r}, "
        f"amount={intent.amount}, "
        f"complaint_type={intent.complaint_type!r}"
    )

    # ── Step 4: Regex fallback if LLM missed the transaction_id ─────────────
    # Even the best LLMs occasionally miss structured fields. Before routing to
    # clarification (which wastes a round-trip), try searching the raw user
    # message directly for known transaction ID patterns.
    # This is NOT a replacement for the LLM — it's a safety net for LLM misses.
    if not intent.transaction_id:
        trace.append(
            "[extract_intent] LLM returned null transaction_id — "
            "running regex fallback on raw user message..."
        )
        # Common patterns: TXN_AUTO_001, TXN123, TXNPAY1234, etc.
        # Match sequences of uppercase letters, digits, and underscores.
        fallback_patterns = [
            # Explicit "transaction ID: XYZ" or "ref: XYZ"
            r"(?:transaction\s*id|txn\s*id|ref(?:erence)?)[:\s#]+([A-Za-z0-9_\-]{3,30})",
            # Bare TXN prefix followed by alphanumerics
            r"\b(TXN[_\-]?[A-Za-z0-9_\-]{2,25})\b",
            # Generic standalone uppercase+digit+underscore token ≥ 6 chars
            r"\b([A-Z][A-Z0-9_\-]{5,29})\b",
        ]
        found_id = None
        for pattern in fallback_patterns:
            match = re.search(pattern, user_message, re.IGNORECASE)
            if match:
                candidate = match.group(1).strip().upper().replace("-", "_")
                # Validate it looks like an ID (no pure words like "PAYMENT")
                if re.match(r"^[A-Z0-9_]{3,30}$", candidate) and any(ch.isdigit() for ch in candidate):
                    found_id = candidate
                    break

        if found_id:
            trace.append(
                f"[extract_intent] Regex fallback found transaction_id={found_id!r}. "
                f"Proceeding with this value."
            )
            return {
                "trace":          trace,
                "transaction_id": found_id,
                "amount":         intent.amount,
                "complaint_type": intent.complaint_type,
                "decision":       None,
            }

        # No ID found by either LLM or regex — route to clarification
        trace.append(
            "[extract_intent] No transaction_id found via LLM or regex. "
            "Routing to clarification."
        )
        return {
            "trace":             trace,
            "transaction_id":    None,
            "amount":            intent.amount,
            "complaint_type":    intent.complaint_type,
            "decision":          "clarify",
            "response_to_user":  (
                "To look up your transaction, I'll need the transaction ID. "
                "You can usually find it in your Paytm app under 'Transaction History'. "
                "It looks something like TXN_AUTO_001 or a similar reference number."
            ),
        }

    # ── All good — pass extracted fields to next node ───────────────────────
    return {
        "trace":          trace,
        "transaction_id": intent.transaction_id,
        "amount":         intent.amount,
        "complaint_type": intent.complaint_type,
        "decision":       None,   # Reset; will be set by policy_decision
    }
