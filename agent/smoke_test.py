"""Smoke test — verifies imports, policy logic, and idempotency WITHOUT needing GROQ_API_KEY."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from mock_data.db import get_connection
from agent.nodes.policy_decision import policy_decision
from agent.nodes.execute_action import _issue_refund

print("=== Policy Decision Smoke Tests ===")
tests = [
    ({"transaction_status": "success",            "amount": 100,   "transaction_id": "X", "trace": []}, "inform_resolved"),
    ({"transaction_status": "failed_pending",     "amount": 100,   "transaction_id": "X", "trace": []}, "inform_pending"),
    ({"transaction_status": "failed_past_window", "amount": 300,   "transaction_id": "X", "trace": []}, "auto_resolve"),
    ({"transaction_status": "failed_past_window", "amount": 12500, "transaction_id": "X", "trace": []}, "escalate"),
    ({"transaction_status": "ambiguous",          "amount": 2100,  "transaction_id": "X", "trace": []}, "escalate"),
    ({"transaction_status": "fraud_flagged",      "amount": 4999,  "transaction_id": "X", "trace": []}, "escalate"),
]
all_pass = True
for state, expected in tests:
    result = policy_decision(state)
    actual = result["decision"]
    ok = actual == expected
    all_pass = all_pass and ok
    prefix = "PASS" if ok else "FAIL"
    print(f"  {prefix} | status={state['transaction_status']!r:<20} amount={state['amount']:<8} -> {actual!r} (expected {expected!r})")

print()
print("=== Idempotency Smoke Test ===")

# Clean up any prior run
conn = get_connection()
conn.execute("DELETE FROM processed_refunds WHERE transaction_id = 'SMOKE_TEST'")
conn.commit()
conn.close()

r1 = _issue_refund("SMOKE_TEST", 42.0)
r2 = _issue_refund("SMOKE_TEST", 42.0)
print(f"  Call 1: already_processed={r1['already_processed']} (expect False)")
print(f"  Call 2: already_processed={r2['already_processed']} (expect True )")
print(f"  Timestamps match: {r1['refund_timestamp'] == r2['refund_timestamp']}")

idempotency_ok = (not r1["already_processed"]) and r2["already_processed"] and (r1["refund_timestamp"] == r2["refund_timestamp"])
all_pass = all_pass and idempotency_ok

# Cleanup
conn = get_connection()
conn.execute("DELETE FROM processed_refunds WHERE transaction_id = 'SMOKE_TEST'")
conn.commit()
conn.close()

print()
result_str = "ALL PASSED" if all_pass else "SOME TESTS FAILED"
print(f"Result: {result_str}")
sys.exit(0 if all_pass else 1)
