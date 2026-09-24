"""
mock_data/db.py
---------------
SQLite connection helper and schema creation.

WHAT IS MOCKED: This SQLite database stands in for real bank/NPCI/UDIR backend
systems. In production, fetch_transaction_status would call NPCI's UPI Status API
and UDIR (Unified Dispute and Issue Resolution) APIs over mTLS. The schema here
mirrors realistic fields those APIs would return.

WHAT IS REAL: The table structure, idempotency tracking via processed_refunds,
and all query logic are written to production-grade standards.
"""

import sqlite3
import os
from pathlib import Path

# Canonical DB path — always resolve relative to this file so imports work
# regardless of the working directory.
DB_PATH = Path(__file__).parent / "upi_disputes.db"


def get_connection() -> sqlite3.Connection:
    """
    Return a SQLite connection with row_factory set to sqlite3.Row so callers
    can access columns by name (e.g., row["status"]) instead of by index.

    The connection is NOT shared across threads — callers are responsible for
    closing it when done, or using it as a context manager.
    """
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    # Enable WAL mode for slightly better concurrent read performance during demo.
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def create_tables() -> None:
    """
    Create the transactions and processed_refunds tables if they don't exist.
    Safe to call multiple times (idempotent).
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()

        # --- transactions table -------------------------------------------------
        # Represents the mock NPCI/bank transaction ledger.
        # status values are the canonical set the policy_decision node consumes:
        #   "success"            — payment completed, funds credited to payee
        #   "failed_pending"     — failure within T+1 reversal window (auto-pending)
        #   "failed_past_window" — failure outside T+1 window; eligible for dispute
        #   "ambiguous"          — conflicting status across mock bank/NPCI records
        #   "fraud_flagged"      — transaction flagged by fraud detection system
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                transaction_id   TEXT PRIMARY KEY,
                status           TEXT NOT NULL CHECK(status IN (
                                     'success', 'failed_pending',
                                     'failed_past_window', 'ambiguous', 'fraud_flagged'
                                 )),
                amount           REAL NOT NULL,
                currency         TEXT NOT NULL DEFAULT 'INR',
                payer_vpa        TEXT NOT NULL,   -- Virtual Payment Address (UPI ID)
                payee_vpa        TEXT NOT NULL,
                payee_name       TEXT NOT NULL,
                initiated_at     TEXT NOT NULL,   -- ISO-8601 UTC timestamp
                description      TEXT,
                bank_ref_number  TEXT             -- Mock bank reference
            )
        """)

        # --- processed_refunds table --------------------------------------------
        # Idempotency ledger. Before executing any refund, execute_action.py checks
        # this table. If the transaction_id already exists here, the refund is NOT
        # re-executed — the cached result is returned instead.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS processed_refunds (
                transaction_id   TEXT PRIMARY KEY,
                refund_timestamp TEXT NOT NULL,   -- ISO-8601 UTC timestamp of refund
                amount           REAL NOT NULL,
                idempotency_key  TEXT NOT NULL    -- == transaction_id; stored explicitly
                                                  --    for audit clarity
            )
        """)

        conn.commit()
    finally:
        conn.close()


# Auto-create tables when this module is imported for the first time.
create_tables()
