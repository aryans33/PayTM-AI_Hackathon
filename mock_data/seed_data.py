"""
mock_data/seed_data.py
----------------------
Seeds the SQLite transactions table with realistic mock data covering all 5
status values that the policy_decision node handles.

Run this script before starting the API server:
    python mock_data/seed_data.py

It is fully idempotent -- safe to re-run; it clears and re-inserts all rows.

WHAT IS MOCKED: All transaction records, bank reference numbers, VPAs, and
timestamps are fabricated. In production, this data would come from NPCI's
Transaction Status API and the bank's core banking system.

WHAT IS REAL: The status values and schema match exactly what the production
policy_decision engine would consume from a real NPCI API response.

Transaction ID convention:
    TXN_OK_xxx       -- success            (inform_resolved)
    TXN_PEND_xxx     -- failed_pending     (inform_pending)
    TXN_AUTO_xxx     -- failed_past_window, amount <= 5000  (auto_resolve)
    TXN_HIGH_xxx     -- failed_past_window, amount >  5000  (escalate)
    TXN_AMB_xxx      -- ambiguous          (escalate)
    TXN_FRAUD_xxx    -- fraud_flagged      (escalate)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from mock_data.db import get_connection

TRANSACTIONS = [

    # ===========================================================================
    # SUCCESS (inform_resolved) -- payment completed, funds credited.
    # ===========================================================================
    {
        "transaction_id":  "TXN_OK_001",
        "status":          "success",
        "amount":          1500.00,
        "currency":        "INR",
        "payer_vpa":       "rahul.sharma@okicici",
        "payee_vpa":       "bigbasket@ybl",
        "payee_name":      "BigBasket Retail Pvt Ltd",
        "initiated_at":    "2026-09-14T10:23:11Z",
        "description":     "Grocery order #BB-29341",
        "bank_ref_number": "ICICI20260914A001",
    },
    {
        "transaction_id":  "TXN_OK_002",
        "status":          "success",
        "amount":          299.00,
        "currency":        "INR",
        "payer_vpa":       "priya.menon@oksbi",
        "payee_vpa":       "swiggy@icici",
        "payee_name":      "Swiggy Internet Pvt Ltd",
        "initiated_at":    "2026-09-14T19:05:44Z",
        "description":     "Food delivery order #SWG-78821",
        "bank_ref_number": "SBI20260914B002",
    },
    {
        "transaction_id":  "TXN_OK_003",
        "status":          "success",
        "amount":          4750.00,
        "currency":        "INR",
        "payer_vpa":       "ananya.iyer@paytm",
        "payee_vpa":       "irctc@sbi",
        "payee_name":      "IRCTC Rail Booking",
        "initiated_at":    "2026-09-13T08:45:00Z",
        "description":     "Train ticket BLR-DEL #IRCTC-221984",
        "bank_ref_number": "PAYTM20260913C003",
    },
    {
        "transaction_id":  "TXN_OK_004",
        "status":          "success",
        "amount":          999.00,
        "currency":        "INR",
        "payer_vpa":       "rohit.verma@okaxis",
        "payee_vpa":       "netflixindia@kotak",
        "payee_name":      "Netflix Services India",
        "initiated_at":    "2026-09-14T00:01:10Z",
        "description":     "Netflix monthly subscription",
        "bank_ref_number": "AXIS20260914D004",
    },
    {
        "transaction_id":  "TXN_OK_005",
        "status":          "success",
        "amount":          249.00,
        "currency":        "INR",
        "payer_vpa":       "kavya.nair@okhdfcbank",
        "payee_vpa":       "pharmeasy@axisbank",
        "payee_name":      "PharmEasy Health",
        "initiated_at":    "2026-09-14T14:38:52Z",
        "description":     "Medicine order #PE-50032",
        "bank_ref_number": "HDFC20260914E005",
    },

    # ===========================================================================
    # FAILED_PENDING (inform_pending) -- within 24h T+1 window, NPCI reversing.
    # ===========================================================================
    {
        "transaction_id":  "TXN_PEND_001",
        "status":          "failed_pending",
        "amount":          800.00,
        "currency":        "INR",
        "payer_vpa":       "arjun.nair@okhdfcbank",
        "payee_vpa":       "zomato@axisbank",
        "payee_name":      "Zomato Ltd",
        "initiated_at":    "2026-09-15T02:14:09Z",
        "description":     "Food order #ZMT-44412",
        "bank_ref_number": "HDFC20260915F001",
    },
    {
        "transaction_id":  "TXN_PEND_002",
        "status":          "failed_pending",
        "amount":          3200.00,
        "currency":        "INR",
        "payer_vpa":       "deepa.krishna@paytm",
        "payee_vpa":       "makemytrip@yesbank",
        "payee_name":      "MakeMyTrip Pvt Ltd",
        "initiated_at":    "2026-09-15T00:30:55Z",
        "description":     "Bus ticket booking #MMT-90021",
        "bank_ref_number": "PAYTM20260915G002",
    },
    {
        "transaction_id":  "TXN_PEND_003",
        "status":          "failed_pending",
        "amount":          150.00,
        "currency":        "INR",
        "payer_vpa":       "sneha.patil@oksbi",
        "payee_vpa":       "bookmyshow@icici",
        "payee_name":      "BookMyShow Entertainment",
        "initiated_at":    "2026-09-15T04:05:33Z",
        "description":     "Movie ticket booking #BMS-33120",
        "bank_ref_number": "SBI20260915H003",
    },
    {
        "transaction_id":  "TXN_PEND_004",
        "status":          "failed_pending",
        "amount":          4999.00,
        "currency":        "INR",
        "payer_vpa":       "kiran.reddy@okhdfcbank",
        "payee_vpa":       "myntra@kotak",
        "payee_name":      "Myntra Designs Pvt Ltd",
        "initiated_at":    "2026-09-15T01:10:00Z",
        "description":     "Fashion order #MYN-67543",
        "bank_ref_number": "HDFC20260915I004",
    },

    # ===========================================================================
    # FAILED_PAST_WINDOW + amount <= 5000 (auto_resolve) -- autonomous refund.
    # ===========================================================================
    {
        "transaction_id":  "TXN_AUTO_001",
        "status":          "failed_past_window",
        "amount":          300.00,
        "currency":        "INR",
        "payer_vpa":       "vikram.rao@oksbi",
        "payee_vpa":       "quickmart@kotak",
        "payee_name":      "QuickMart Online Store",
        "initiated_at":    "2026-09-12T15:42:30Z",
        "description":     "Online purchase #QM-11204",
        "bank_ref_number": "SBI20260912J001",
    },
    {
        "transaction_id":  "TXN_AUTO_002",
        "status":          "failed_past_window",
        "amount":          75.00,
        "currency":        "INR",
        "payer_vpa":       "pooja.singh@okaxis",
        "payee_vpa":       "ola@axisbank",
        "payee_name":      "Ola Cabs Pvt Ltd",
        "initiated_at":    "2026-09-11T22:55:10Z",
        "description":     "Cab ride #OLA-87234",
        "bank_ref_number": "AXIS20260911K002",
    },
    {
        "transaction_id":  "TXN_AUTO_003",
        "status":          "failed_past_window",
        "amount":          1200.00,
        "currency":        "INR",
        "payer_vpa":       "anil.kumar@paytm",
        "payee_vpa":       "dominos@hdfc",
        "payee_name":      "Domino's Pizza India",
        "initiated_at":    "2026-09-10T20:00:00Z",
        "description":     "Pizza order #DOM-55302",
        "bank_ref_number": "PAYTM20260910L003",
    },
    {
        "transaction_id":  "TXN_AUTO_004",
        "status":          "failed_past_window",
        "amount":          4850.00,
        "currency":        "INR",
        "payer_vpa":       "meera.bose@okhdfcbank",
        "payee_vpa":       "nykaa@icici",
        "payee_name":      "Nykaa Fashion Ltd",
        "initiated_at":    "2026-09-09T11:30:00Z",
        "description":     "Beauty products #NYK-34201",
        "bank_ref_number": "HDFC20260909M004",
    },
    {
        "transaction_id":  "TXN_AUTO_005",
        "status":          "failed_past_window",
        "amount":          499.00,
        "currency":        "INR",
        "payer_vpa":       "suresh.iyer@oksbi",
        "payee_vpa":       "hotstar@axisbank",
        "payee_name":      "Disney+ Hotstar",
        "initiated_at":    "2026-09-08T07:15:22Z",
        "description":     "Hotstar annual subscription",
        "bank_ref_number": "SBI20260908N005",
    },
    {
        "transaction_id":  "TXN_AUTO_006",
        "status":          "failed_past_window",
        "amount":          2750.00,
        "currency":        "INR",
        "payer_vpa":       "neha.jain@okaxis",
        "payee_vpa":       "lenskart@kotak",
        "payee_name":      "Lenskart Solutions Pvt Ltd",
        "initiated_at":    "2026-09-07T16:42:00Z",
        "description":     "Eyewear order #LENS-20034",
        "bank_ref_number": "AXIS20260907O006",
    },

    # ===========================================================================
    # FAILED_PAST_WINDOW + amount > 5000 (escalate) -- high-value, human review.
    # ===========================================================================
    {
        "transaction_id":  "TXN_HIGH_001",
        "status":          "failed_past_window",
        "amount":          12500.00,
        "currency":        "INR",
        "payer_vpa":       "sunita.joshi@okhdfcbank",
        "payee_vpa":       "airtickets@axisbank",
        "payee_name":      "AirTickets Booking Portal",
        "initiated_at":    "2026-09-10T08:17:22Z",
        "description":     "Flight booking DEL-BOM #AT-55501",
        "bank_ref_number": "HDFC20260910P001",
    },
    {
        "transaction_id":  "TXN_HIGH_002",
        "status":          "failed_past_window",
        "amount":          28000.00,
        "currency":        "INR",
        "payer_vpa":       "rajesh.khanna@paytm",
        "payee_vpa":       "reliancedigital@sbi",
        "payee_name":      "Reliance Digital Retail",
        "initiated_at":    "2026-09-08T14:30:00Z",
        "description":     "Laptop purchase #RD-91234",
        "bank_ref_number": "PAYTM20260908Q002",
    },
    {
        "transaction_id":  "TXN_HIGH_003",
        "status":          "failed_past_window",
        "amount":          7500.00,
        "currency":        "INR",
        "payer_vpa":       "lalitha.rao@okicici",
        "payee_vpa":       "goibibo@yesbank",
        "payee_name":      "Goibibo Travel Services",
        "initiated_at":    "2026-09-07T09:00:00Z",
        "description":     "Hotel booking Chennai #GOI-41203",
        "bank_ref_number": "ICICI20260907R003",
    },
    {
        "transaction_id":  "TXN_HIGH_004",
        "status":          "failed_past_window",
        "amount":          55000.00,
        "currency":        "INR",
        "payer_vpa":       "vikrant.malhotra@okhdfcbank",
        "payee_vpa":       "tanishq@icici",
        "payee_name":      "Tanishq Jewellery",
        "initiated_at":    "2026-09-05T12:10:00Z",
        "description":     "Jewellery purchase #TAN-10022",
        "bank_ref_number": "HDFC20260905S004",
    },

    # ===========================================================================
    # AMBIGUOUS (escalate) -- conflicting records between bank and NPCI.
    # ===========================================================================
    {
        "transaction_id":  "TXN_AMB_001",
        "status":          "ambiguous",
        "amount":          2100.00,
        "currency":        "INR",
        "payer_vpa":       "manish.gupta@okaxis",
        "payee_vpa":       "rentpay@ybl",
        "payee_name":      "RentPay Housing Solutions",
        "initiated_at":    "2026-09-11T12:00:00Z",
        "description":     "Rent payment Sept 2026",
        "bank_ref_number": "AXIS20260911T001",
    },
    {
        "transaction_id":  "TXN_AMB_002",
        "status":          "ambiguous",
        "amount":          640.00,
        "currency":        "INR",
        "payer_vpa":       "divya.pillai@oksbi",
        "payee_vpa":       "urbanclap@axisbank",
        "payee_name":      "Urban Company (UrbanClap)",
        "initiated_at":    "2026-09-12T17:45:00Z",
        "description":     "Home cleaning service #UC-77230",
        "bank_ref_number": "SBI20260912U002",
    },
    {
        "transaction_id":  "TXN_AMB_003",
        "status":          "ambiguous",
        "amount":          9800.00,
        "currency":        "INR",
        "payer_vpa":       "sanjay.mehta@paytm",
        "payee_vpa":       "cleartrip@hdfc",
        "payee_name":      "Cleartrip Pvt Ltd",
        "initiated_at":    "2026-09-10T06:30:00Z",
        "description":     "Flight + hotel package #CT-30019",
        "bank_ref_number": "PAYTM20260910V003",
    },

    # ===========================================================================
    # FRAUD_FLAGGED (escalate) -- risk system flagged, zero autonomous action.
    # ===========================================================================
    {
        "transaction_id":  "TXN_FRAUD_001",
        "status":          "fraud_flagged",
        "amount":          4999.00,
        "currency":        "INR",
        "payer_vpa":       "user.unknown@paytm",
        "payee_vpa":       "suspiciousmerchant@ibl",
        "payee_name":      "Unknown Merchant XYZ",
        "initiated_at":    "2026-09-13T03:22:47Z",
        "description":     "Transfer to unverified entity",
        "bank_ref_number": "PAYTM20260913W001",
    },
    {
        "transaction_id":  "TXN_FRAUD_002",
        "status":          "fraud_flagged",
        "amount":          18500.00,
        "currency":        "INR",
        "payer_vpa":       "victim.user@okicici",
        "payee_vpa":       "phishing-site@bob",
        "payee_name":      "Phishing Fake Store",
        "initiated_at":    "2026-09-14T01:11:00Z",
        "description":     "Unauthorized transfer",
        "bank_ref_number": "ICICI20260914X002",
    },
    {
        "transaction_id":  "TXN_FRAUD_003",
        "status":          "fraud_flagged",
        "amount":          999.00,
        "currency":        "INR",
        "payer_vpa":       "ankit.soni@oksbi",
        "payee_vpa":       "fake-recharge@rbl",
        "payee_name":      "Fake Mobile Recharge",
        "initiated_at":    "2026-09-13T23:55:00Z",
        "description":     "Mobile recharge scam attempt",
        "bank_ref_number": "SBI20260913Y003",
    },
]


def seed() -> None:
    conn = get_connection()
    try:
        cursor = conn.cursor()

        # Clear existing data (idempotent re-seeding)
        cursor.execute("DELETE FROM processed_refunds")
        cursor.execute("DELETE FROM transactions")

        cursor.executemany(
            """
            INSERT INTO transactions
                (transaction_id, status, amount, currency, payer_vpa, payee_vpa,
                 payee_name, initiated_at, description, bank_ref_number)
            VALUES
                (:transaction_id, :status, :amount, :currency, :payer_vpa, :payee_vpa,
                 :payee_name, :initiated_at, :description, :bank_ref_number)
            """,
            TRANSACTIONS,
        )
        conn.commit()

        # Group by status for the summary table
        by_status = {}
        for t in TRANSACTIONS:
            by_status.setdefault(t["status"], []).append(t)

        print(f"[OK] Seeded {len(TRANSACTIONS)} transactions into mock DB.")
        from mock_data.db import DB_PATH
        print(f"     DB path: {DB_PATH}")
        print()
        print(f"  {'Transaction ID':<22} {'Status':<22} {'Amount (INR)':>12}  Decision Path")
        print(f"  {'-'*22} {'-'*22} {'-'*12}  {'-'*30}")
        for t in TRANSACTIONS:
            status = t["status"]
            amount = t["amount"]
            if status == "success":
                path = "inform_resolved"
            elif status == "failed_pending":
                path = "inform_pending"
            elif status == "failed_past_window" and amount <= 5000:
                path = "auto_resolve"
            elif status == "failed_past_window" and amount > 5000:
                path = "escalate (high-value)"
            elif status == "ambiguous":
                path = "escalate (ambiguous)"
            elif status == "fraud_flagged":
                path = "escalate (fraud)"
            else:
                path = "escalate (unknown)"
            print(f"  {t['transaction_id']:<22} {status:<22} Rs.{amount:>9,.2f}  {path}")

        print()
        print(f"  Summary: {len(by_status.get('success',[]))} success | "
              f"{len(by_status.get('failed_pending',[]))} pending | "
              f"{len([t for t in TRANSACTIONS if t['status']=='failed_past_window' and t['amount']<=5000])} auto_resolve | "
              f"{len([t for t in TRANSACTIONS if t['status']=='failed_past_window' and t['amount']>5000])} high-value | "
              f"{len(by_status.get('ambiguous',[]))} ambiguous | "
              f"{len(by_status.get('fraud_flagged',[]))} fraud")
    finally:
        conn.close()


if __name__ == "__main__":
    seed()
