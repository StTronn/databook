"""Razorpay pack: dashboard report exports (.xlsx, major units, IST day-first text dates) and
API / `razorpay` CLI JSON (minor units, unix seconds)."""
from __future__ import annotations

from pathlib import Path

from databook.packs import Kind

HERE = Path(__file__).parent

_TEXT = "id entity_id order_id payment_id settlement_id invoice_id card_id customer_id plan_id offer_id " \
        "subscription_id dispute_id refund_id receipt arn utr settlement_utr contact customer_contact vpa " \
        "email customer_email bank wallet error_code error_description method status type currency " \
        "card_network card_issuer card_type issuer_name"
_MONEY = "amount amount_refunded amount_transferred amount_paid amount_due fee tax fees debit credit " \
         "fee_exclusive_tax plan_amount"
_TS = "created_at settled_at captured_at entity_created_at payment_captured_at dispute_created_at start_at " \
      "end_at charge_at authenticated_at activated_at cancelled_at"
_BOOL = "captured international settled on_hold customer_notify"
_INT = "attempts quantity total_count paid_count plan_interval"

EXPORT = {**dict.fromkeys(_TEXT.split(), "text"), **dict.fromkeys(_MONEY.split(), "money"),
          **dict.fromkeys(_TS.split(), "local:dmy"), **dict.fromkeys(_BOOL.split(), "bool"),
          **dict.fromkeys(_INT.split(), "int"), "notes": "json", "card": "json"}
JSON = {**dict.fromkeys(_TS.split(), "unix")}   # money stays "money": minor units are handled by row context


def _k(table, fp, entity=None, key=("id",)):
    return Kind(table, frozenset(fp.split()), EXPORT, entity, JSON, key)


class RazorpayPack:
    name = "razorpay"
    timezone = "Asia/Kolkata"
    skill_ref = HERE / "skill.md"
    templates = HERE / "templates"
    kinds = {
        "payments": _k("payments", "id amount currency status order_id method amount_refunded captured fee tax created_at", "payment"),
        "orders": _k("orders", "id amount amount_paid amount_due currency receipt status attempts created_at", "order"),
        "refunds": _k("refunds", "id amount currency payment_id created_at arn", "refund"),
        "settlements": _k("settlements", "id amount status fees tax utr created_at", "settlement"),
        "combined": _k("combined", "entity_id type debit credit amount currency fee tax settled settlement_id",
                       key=("entity_id", "type")),
        "recon": _k("settlement_recon", "transaction_entity entity_id amount debit credit settlement_id settled_at settlement_utr",
                    key=("transaction_entity", "entity_id", "settlement_id")),
        "subscriptions": _k("subscriptions", "subscription_id status plan_id plan_amount plan_period total_count paid_count start_at",
                            "subscription", key=("subscription_id",)),
    }


PACK = RazorpayPack()
