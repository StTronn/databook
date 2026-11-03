"""Synthetic Razorpay dashboard exports for demos and tests (clearly fake: example.com, seeded RNG).

Mirrors real export quirks: day-first text dates (orders), Excel datetimes (payments/combined),
`=+91…` contact formulas, 0/1 floats for booleans, amounts as text in the orders report.
"""
from __future__ import annotations

import random
import string
from datetime import datetime, timedelta
from pathlib import Path

from openpyxl import Workbook

PRICES, PRICE_W = [499, 999, 1499, 1799, 2499, 3999], [10, 22, 25, 18, 15, 10]
METHODS, METHOD_W = ["upi", "card", "netbanking"], [58, 29, 13]
SUCCESS = {"upi": 0.80, "card": 0.66, "netbanking": 0.82}
ERRORS = {"upi": ["Payment was not completed on time", "UPI app declined the request"],
          "card": ["Card declined by bank", "Payment failed due to incorrect OTP", "Payment cancelled by user"],
          "netbanking": ["Bank server unavailable", "Payment cancelled by user"]}


def _id(rng, prefix):
    return prefix + "".join(rng.choices(string.ascii_letters + string.digits, k=14))


def generate(seed: int = 7, n_orders: int = 1240, month: tuple[int, int] = (2026, 5)) -> dict[str, list[dict]]:
    rng = random.Random(seed)
    y, m = month
    start = datetime(y, m, 1)
    days = (datetime(y + (m == 12), m % 12 + 1, 1) - start).days
    orders, payments, refunds, combined = [], [], [], []

    def pay(order_id, amount, method, at, ok):
        p = {"id": _id(rng, "pay_"), "amount": float(amount), "currency": "INR", "order_id": order_id, "method": method,
             "captured": ok, "status": "captured" if ok else "failed", "created_at": at, "amount_refunded": 0.0,
             "refund_status": None, "email": f"customer{rng.randint(1, 900)}@example.com",
             "contact": f"=+9198{rng.randint(10000000, 99999999)}",
             "fee": round(amount * 0.02, 2) if ok else None, "tax": round(amount * 0.02 * 0.18, 2) if ok else None,
             "error_code": None if ok else "BAD_REQUEST_ERROR",
             "error_description": None if ok else rng.choice(ERRORS[method])}
        payments.append(p)
        return p

    for _ in range(n_orders):
        at = start + timedelta(seconds=rng.randrange(days * 86400))
        amount = rng.choices(PRICES, PRICE_W)[0]
        o = {"id": _id(rng, "order_"), "amount": amount, "status": "created", "attempts": 0, "created_at": at,
             "receipt": f"rcpt_{rng.randint(10000, 99999)}"}
        orders.append(o)
        if rng.random() < 0.73:
            method, t = rng.choices(METHODS, METHOD_W)[0], at
            for attempt in range(3):
                t += timedelta(seconds=rng.randint(20, 600))
                ok = rng.random() < SUCCESS[method]
                pay(o["id"], amount, method, t, ok)
                o["attempts"] += 1
                if ok:
                    o["status"] = "paid"
                    break
                o["status"] = "attempted"
                if rng.random() > 0.35:
                    break
                if rng.random() < 0.4:
                    method = rng.choices(METHODS, METHOD_W)[0]
    for _ in range(40):  # payment links: no order
        pay(None, rng.choices(PRICES, PRICE_W)[0], "upi", start + timedelta(seconds=rng.randrange(days * 86400)), True)
    for p in payments:
        if p["captured"] and rng.random() < 0.03:
            p["status"], p["amount_refunded"], p["refund_status"] = "refunded", p["amount"], "full"
            r = {"id": _id(rng, "rfnd_"), "amount": p["amount"], "payment_id": p["id"],
                 "created_at": p["created_at"] + timedelta(days=rng.randint(1, 5))}
            refunds.append(r)
    settle_by = start + timedelta(days=days - 2)
    for p in payments:
        if p["captured"]:
            settled = p["created_at"] < settle_by
            combined.append({"entity_id": p["id"], "type": "payment", "debit": 0.0,
                             "credit": round(p["amount"] - p["fee"] - p["tax"], 2), "amount": p["amount"],
                             "fee": p["fee"], "tax": p["tax"], "settled": 1.0 if settled else 0.0,
                             "created_at": p["created_at"],
                             "settlement_id": _id(rng, "setl_") if settled else None, "payment_id": None,
                             "order_id": p["order_id"], "method": p["method"]})
    for r in refunds:
        combined.append({"entity_id": r["id"], "type": "refund", "debit": r["amount"], "credit": 0.0, "amount": r["amount"],
                         "fee": 0.0, "tax": 0.0, "settled": 0.0, "created_at": r["created_at"], "settlement_id": None,
                         "payment_id": r["payment_id"], "order_id": None, "method": None})
    return {"orders": orders, "payments": payments, "refunds": refunds, "combined": combined}


def _xlsx(path: Path, headers: list[str], rows: list[list]) -> None:
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for r in rows:
        ws.append(r)
    wb.save(path)


def write_exports(data: dict, out: Path) -> list[str]:
    out.mkdir(parents=True, exist_ok=True)
    dmy = lambda d: d.strftime("%d/%m/%Y %H:%M:%S")
    money = lambda v: f"{v:.2f}"
    _xlsx(out / "orders.xlsx", ["id", "amount", "amount_paid", "amount_due", "currency", "receipt", "offer_id", "status",
                                "attempts", "notes", "created_at"],
          [[o["id"], money(o["amount"]), money(o["amount"] if o["status"] == "paid" else 0),
            money(0 if o["status"] == "paid" else o["amount"]), "INR", o["receipt"], None, o["status"],
            float(o["attempts"]), "[]", dmy(o["created_at"])] for o in data["orders"]])
    _xlsx(out / "payments.xlsx", ["id", "amount", "currency", "status", "order_id", "invoice_id", "international", "method",
                                  "amount_refunded", "amount_transferred", "refund_status", "captured", "description",
                                  "card_id", "bank", "wallet", "vpa", "email", "contact", "notes", "fee", "tax",
                                  "error_code", "error_description", "created_at"],
          [[p["id"], p["amount"], "INR", p["status"], p["order_id"], None, 0.0, p["method"], p["amount_refunded"], 0.0,
            p["refund_status"], 1.0 if p["captured"] else 0.0, None, None, None, None, None, p["email"], p["contact"],
            "[]", p["fee"], p["tax"], p["error_code"], p["error_description"], p["created_at"]] for p in data["payments"]])
    _xlsx(out / "refunds.xlsx", ["id", "amount", "currency", "payment_id", "notes", "receipt", "created_at", "arn"],
          [[r["id"], money(r["amount"]), "INR", r["payment_id"], "[]", None, dmy(r["created_at"]),
            str(random.Random(r["id"]).randint(10**11, 10**12 - 1))] for r in data["refunds"]])
    _xlsx(out / "combined.xlsx", ["entity_id", "type", "debit", "credit", "amount", "currency", "fee", "tax", "on_hold",
                                  "settled", "created_at", "settled_at", "settlement_id", "description", "notes",
                                  "payment_id", "arn", "settlement_utr", "order_id", "order_receipt", "method"],
          [[c["entity_id"], c["type"], c["debit"], c["credit"], c["amount"], "INR", c["fee"], c["tax"], 0.0, c["settled"],
            c["created_at"], (c["created_at"] + timedelta(days=2)).replace(hour=0, minute=0, second=0)
            if c["settled"] else None, c["settlement_id"], None, "[]", c["payment_id"], None, None, c["order_id"], None,
            c["method"]] for c in data["combined"]])
    return [f"data/{n}.xlsx" for n in ("orders", "payments", "refunds", "combined")]
