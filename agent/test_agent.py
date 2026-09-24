"""
agent/test_agent.py
--------------------
Standalone test script for the LangGraph agent.

Run from the project root (with .env set):
    python agent/test_agent.py

Tests:
    1. Scenario A — auto-resolve (TXN_AUTO_001: failed_past_window, ₹300)
    2. Scenario B — high-value escalation (TXN_HIGH_001: failed_past_window, ₹12,500)
    3. Scenario B alt — ambiguous escalation (TXN_AMB_001)
    4. Scenario C — fraud escalation (TXN_FRAUD_001)
    5. Missing transaction ID — clarification routing
    6. ⭐ IDEMPOTENCY TEST — calls issue_refund twice for same transaction_id,
       asserts the second call returns cached result without executing again.

No API server needed — this talks directly to the LangGraph graph.
Requires: .env with GROQ_API_KEY, and the mock DB seeded (python mock_data/seed_data.py).
"""

import sys
import os
import uuid
from pathlib import Path

# Ensure project root is on the path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from agent.graph import run_agent_sync

# ANSI color helpers
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"


def section(title: str) -> None:
    print(f"\n{BOLD}{CYAN}{'='*70}{RESET}")
    print(f"{BOLD}{CYAN}  {title}{RESET}")
    print(f"{BOLD}{CYAN}{'='*70}{RESET}")


def print_result(result: dict, expected_decision: str) -> bool:
    """Print result and assert decision matches expected. Returns True if passed."""
    actual = result.get("decision", "")
    passed = actual == expected_decision

    status_str = f"{GREEN}PASS{RESET}" if passed else f"{RED}FAIL{RESET}"
    print(f"\n  Decision      : {BOLD}{actual}{RESET}  [{status_str}]")
    print(f"  Expected      : {expected_decision}")
    print(f"  Transaction   : {result.get('transaction_id')}")
    # Use `or 0` to guard against None values (key exists but value is None)
    amount = result.get('amount') or 0
    print(f"  Amount        : Rs.{amount:,.2f}")

    if result.get("escalation_reason"):
        reason = result['escalation_reason']
        print(f"  Escalation    : {reason[:120]}{'...' if len(reason) > 120 else ''}")

    print(f"\n  {YELLOW}-- Trace ---------------------------------------------------{RESET}")
    for line in result.get("trace", []):
        # Sanitize non-ASCII chars for Windows cp1252 console
        safe_line = line.encode('ascii', errors='replace').decode('ascii')
        print(f"    {safe_line}")

    print(f"\n  {YELLOW}-- Response to User ----------------------------------------{RESET}")
    response = result.get('response_to_user', '') or ''
    safe_response = response.encode('ascii', errors='replace').decode('ascii')
    print(f"    {safe_response}")

    return passed


def test_idempotency() -> bool:
    """
    ⭐ IDEMPOTENCY TEST — explicitly required by the hackathon brief.

    Calls issue_refund twice for TXN_AUTO_001 and asserts:
        1. First call: already_processed == False (new refund executed)
        2. Second call: already_processed == True (cached result returned)
        3. The processed_refunds table has exactly ONE row for this transaction
    """
    section("TEST 6 - IDEMPOTENCY: Double-call issue_refund for same transaction_id")
    print(f"\n  {YELLOW}This test calls issue_refund() directly (not via the graph){RESET}")
    print(f"  to verify idempotency at the function level.\n")

    from agent.nodes.execute_action import _issue_refund
    from mock_data.db import get_connection

    txn_id = "TXN_IDEMPOTENCY_TEST"
    amount = 999.99

    # Clean up any prior test run
    conn = get_connection()
    try:
        conn.execute("DELETE FROM processed_refunds WHERE transaction_id = ?", (txn_id,))
        conn.commit()
    finally:
        conn.close()

    # ── First call ───────────────────────────────────────────────────────────
    print(f"  {CYAN}First call: _issue_refund({txn_id!r}, {amount}){RESET}")
    result1 = _issue_refund(txn_id, amount)
    print(f"    success          : {result1['success']}")
    print(f"    already_processed: {result1['already_processed']}")
    print(f"    refund_timestamp : {result1['refund_timestamp']}")

    assert result1["success"] is True,           "First call: success should be True"
    assert result1["already_processed"] is False, "First call: should NOT be a duplicate"
    print(f"    {GREEN}[PASS] First call asserts passed.{RESET}")

    # ── Second call (the critical check) ─────────────────────────────────────
    print(f"\n  {CYAN}Second call (same txn_id): _issue_refund({txn_id!r}, {amount}){RESET}")
    result2 = _issue_refund(txn_id, amount)
    print(f"    success          : {result2['success']}")
    print(f"    already_processed: {result2['already_processed']}")
    print(f"    refund_timestamp : {result2['refund_timestamp']}")

    assert result2["success"] is True,           "Second call: success should be True (cached)"
    assert result2["already_processed"] is True,  "Second call: MUST be flagged as duplicate"
    assert result2["refund_timestamp"] == result1["refund_timestamp"], \
        "Second call: timestamp must match first call (proves cached result)"
    print(f"    {GREEN}[PASS] Second call asserts passed -- idempotency confirmed.{RESET}")

    # ── Verify DB has exactly one row ────────────────────────────────────────
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) as cnt FROM processed_refunds WHERE transaction_id = ?",
            (txn_id,),
        )
        row_count = cursor.fetchone()["cnt"]
    finally:
        conn.close()

    assert row_count == 1, f"DB should have exactly 1 row for this txn_id, got {row_count}"
    print(f"\n  {GREEN}[PASS] Database row count = {row_count} (exactly 1 -- no duplicate insertion).{RESET}")
    print(f"\n  {GREEN}{BOLD}IDEMPOTENCY TEST: PASSED{RESET}")

    # Clean up
    conn = get_connection()
    try:
        conn.execute("DELETE FROM processed_refunds WHERE transaction_id = ?", (txn_id,))
        conn.commit()
    finally:
        conn.close()

    return True


def main() -> None:
    results = []

    # Scenario A: Auto-resolve
    section("TEST 1 - Scenario A: Auto-resolve (TXN_AUTO_001, Rs.300, failed_past_window)")
    print("  User says: 'My Rs.300 payment to QuickMart failed, transaction ID TXN_AUTO_001'")
    r = run_agent_sync(
        "My Rs.300 payment to QuickMart didn't go through but money got deducted, transaction ID TXN_AUTO_001",
        thread_id=f"test-A-{uuid.uuid4()}",
    )
    results.append(print_result(r, expected_decision="auto_resolve"))

    # Scenario B: High-value escalation
    section("TEST 2 - Scenario B: High-value escalation (TXN_HIGH_001, Rs.12500, failed_past_window)")
    print("  User says: 'My flight booking payment of Rs.12500 failed, transaction TXN_HIGH_001'")
    r = run_agent_sync(
        "My flight booking payment of Rs.12500 failed but money was deducted, transaction TXN_HIGH_001",
        thread_id=f"test-B1-{uuid.uuid4()}",
    )
    results.append(print_result(r, expected_decision="escalate"))

    # Scenario B alt: Ambiguous
    section("TEST 3 - Scenario B alt: Ambiguous escalation (TXN_AMB_001)")
    print("  User says: 'I have a dispute about my rent payment TXN_AMB_001'")
    r = run_agent_sync(
        "My rent payment didn't go through, transaction ID TXN_AMB_001",
        thread_id=f"test-B2-{uuid.uuid4()}",
    )
    results.append(print_result(r, expected_decision="escalate"))

    # Scenario C: Fraud
    section("TEST 4 - Scenario C: Fraud escalation (TXN_FRAUD_001)")
    print("  User says: 'Please refund my transaction TXN_FRAUD_001'")
    r = run_agent_sync(
        "I need a refund for transaction TXN_FRAUD_001",
        thread_id=f"test-C-{uuid.uuid4()}",
    )
    results.append(print_result(r, expected_decision="escalate"))

    # Missing transaction ID
    section("TEST 5 - Missing transaction ID (clarification routing)")
    print("  User says: 'My payment failed, please help'")
    r = run_agent_sync(
        "My payment failed and money was deducted but I didn't get the service",
        thread_id=f"test-clarify-{uuid.uuid4()}",
    )
    results.append(print_result(r, expected_decision="clarify"))

    # ── Idempotency test ─────────────────────────────────────────────────────
    idempotency_passed = test_idempotency()
    results.append(idempotency_passed)

    # ── Summary ──────────────────────────────────────────────────────────────
    section("TEST SUMMARY")
    labels = [
        "Scenario A (auto_resolve)",
        "Scenario B (escalate: high-value)",
        "Scenario B alt (escalate: ambiguous)",
        "Scenario C (escalate: fraud)",
        "Missing txn ID (clarify)",
        "Idempotency (double-call)",
    ]
    passed = 0
    for i, (label, ok) in enumerate(zip(labels, results)):
        icon = f"{GREEN}[PASS]{RESET}" if ok else f"{RED}[FAIL]{RESET}"
        print(f"  {icon}  Test {i+1}: {label}")
        if ok:
            passed += 1

    total = len(results)
    print(f"\n  {BOLD}{passed}/{total} tests passed.{RESET}")
    if passed < total:
        print(f"  {RED}{BOLD}[!] Some tests FAILED -- check output above.{RESET}")
        sys.exit(1)
    else:
        print(f"  {GREEN}{BOLD}[OK] All tests passed! Agent is ready for demo.{RESET}")



if __name__ == "__main__":
    main()
