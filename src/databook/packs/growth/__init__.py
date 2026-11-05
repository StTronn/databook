"""Growth source packs: each vendor's de facto raw export, typed exactly. Tables are prefixed by vendor.

shopify     Admin → Orders → Export (CSV, one row per line item)
stripe      Dashboard → Payments → Export (unified_payments.csv) + `stripe <resource> list` API JSON
ga4         BigQuery export events_* (`bq query --format=json` / `bq extract` NDJSON; parquet loads as-is)
meta_ads    Ads Manager → Export table data (CSV/XLSX)
google_ads  Reports → Download (CSV, incl. UTF-16 "Excel CSV")
"""
from __future__ import annotations

import re
from pathlib import Path

from databook.packs import Kind

HERE = Path(__file__).parent


def _types(**groups: str) -> dict[str, str]:
    return {c: t for t, cols in groups.items() for c in cols.split()}


# ── Shopify ────────────────────────────────────────────────────────────────────────────────────────────────────
SHOPIFY = {**_types(
    text="id name email phone financial_status fulfillment_status currency discount_code shipping_method "
         "lineitem_name lineitem_sku lineitem_fulfillment_status billing_name billing_zip billing_city billing_province "
         "billing_country billing_phone shipping_name shipping_zip shipping_city shipping_province shipping_country "
         "shipping_phone payment_method payment_reference payment_id vendor tags source risk_level receipt_number "
         "device_id location employee notes note_attributes",
    local="created_at paid_at fulfilled_at cancelled_at",
    int="lineitem_quantity",
    bool="accepts_marketing lineitem_requires_shipping lineitem_taxable",
), **{c: "decimal:2" for c in "subtotal shipping taxes total discount_amount refunded_amount outstanding_balance "
                              "lineitem_price lineitem_compare_at_price lineitem_discount".split()}}


class ShopifyPack:
    name, timezone, skill_ref, templates = "shopify", None, HERE / "shopify.md", None
    kinds = {"orders": Kind("shopify_order_lines", frozenset(
        "name email financial_status paid_at created_at lineitem_quantity lineitem_name lineitem_price total".split()),
        SHOPIFY, key=())}


# ── Stripe ─────────────────────────────────────────────────────────────────────────────────────────────────────
STRIPE_EXPORT = _types(
    text="id currency converted_currency status customer_id customer_email customer_description invoice_id "
         "paymentintent_id payment_intent_id card_id description decline_reason seller_message statement_descriptor mode",
    utc="created_date_utc refunded_date_utc",
    money="amount amount_refunded converted_amount converted_amount_refunded fee taxes_on_fee",
    bool="captured",
)
STRIPE_API = _types(   # API objects: integer minor units ("money" + row currency), unix seconds
    money="amount amount_captured amount_refunded amount_received amount_capturable amount_due amount_paid "
          "amount_remaining subtotal total tax starting_balance ending_balance balance",
    unix="created canceled_at cancel_at current_period_start current_period_end ended_at start_date trial_start "
         "trial_end period_start period_end due_date billing_cycle_anchor",
    text="id customer invoice payment_intent charge subscription status currency email balance_transaction",
    bool="paid refunded captured livemode cancel_at_period_end delinquent",
)


def _api(table: str, obj: str) -> Kind:
    return Kind(table, frozenset(), STRIPE_API, f"object:{obj}", STRIPE_API)


class StripePack:
    name, timezone, skill_ref, templates = "stripe", None, HERE / "stripe.md", None
    kinds = {
        "payments": Kind("stripe_payments", frozenset(
            "id created_date_utc amount amount_refunded currency captured fee status customer_id".split()), STRIPE_EXPORT),
        "charges": _api("stripe_charges", "charge"),
        "refunds": _api("stripe_refunds", "refund"),
        "customers": _api("stripe_customers", "customer"),
        "subscriptions": _api("stripe_subscriptions", "subscription"),
        "invoices": _api("stripe_invoices", "invoice"),
        "payment_intents": _api("stripe_payment_intents", "payment_intent"),
    }


# ── GA4 (BigQuery export) ──────────────────────────────────────────────────────────────────────────────────────
GA4 = _types(
    yyyymmdd="event_date",
    unix_us="event_timestamp event_previous_timestamp user_first_touch_timestamp",
    text="event_name user_pseudo_id user_id stream_id platform",
    int="event_bundle_sequence_id event_server_timestamp_offset batch_event_index batch_ordering_id batch_page_id",
    json="event_params user_properties user_ltv device geo app_info traffic_source collected_traffic_source "
         "session_traffic_source_last_click event_dimensions ecommerce items privacy_info publisher",
)


class GA4Pack:
    name, timezone, skill_ref, templates = "ga4", None, HERE / "ga4.md", None
    kinds = {"events": Kind("ga4_events", frozenset("event_date event_timestamp event_name event_params user_pseudo_id".split()),
                            GA4, json_columns=GA4, key=())}


# ── Ads ────────────────────────────────────────────────────────────────────────────────────────────────────────
def _meta_prepare(t) -> None:
    """Spend columns carry the account currency in their header ("Amount spent (USD)"): strip it, add `currency`."""
    curs = {m[1] for h in t.headers if (m := re.fullmatch(r"amount_spent_([a-z]{3})", h))}
    if len(curs) != 1:
        return                      # no spend column, or several currencies: leave headers as exported
    cur = curs.pop()
    t.headers = [h[: -len(cur) - 1] if h.endswith("_" + cur) else h for h in t.headers]
    if "currency" not in t.headers:
        t.headers.append("currency")
        t.original.append("currency (from spend header)")
        t.rows = [r + [cur.upper()] for r in t.rows]


def _gads_prepare(t) -> None:
    """Drop summary rows (first filled cell "Total: …"); "--" means no value."""
    n = len(t.rows)
    first = lambda r: next((v for v in r if v not in (None, "")), "")                     # noqa: E731
    t.rows = [[None if isinstance(v, str) and v.strip() == "--" else v for v in r] for r in t.rows
              if not str(first(r)).startswith("Total:")]
    if len(t.rows) != n:
        t.warnings.append(f"dropped {n - len(t.rows)} 'Total:' summary row(s)")


class MetaAdsPack:
    name, timezone, skill_ref, templates = "meta_ads", None, HERE / "ads.md", None
    kinds = {"insights": Kind("meta_ads", frozenset("reporting_starts reporting_ends impressions".split()),
                              _types(text="campaign_name ad_set_name ad_name campaign_id ad_set_id ad_id account_id account_name",
                                     timestamp="day reporting_starts reporting_ends",
                                     int="impressions reach link_clicks results clicks_all",
                                     **{"decimal:2": "amount_spent", "decimal:6": "frequency"}),
                              key=(), prepare=_meta_prepare)}


class GoogleAdsPack:
    name, timezone, skill_ref, templates = "google_ads", None, HERE / "ads.md", None
    kinds = {"report": Kind("google_ads", frozenset("campaign impr clicks cost".split()),
                            _types(text="campaign campaign_id ad_group ad_group_id customer_id account currency_code "
                                        "campaign_type campaign_status", timestamp="day", int="impr clicks",
                                   **{"decimal:2": "cost", "decimal:6": "conversions conv_value all_conv all_conv_value"}),
                            key=(), prepare=_gads_prepare)}


SHOPIFY_PACK, STRIPE_PACK, GA4_PACK = ShopifyPack(), StripePack(), GA4Pack()
META_ADS_PACK, GOOGLE_ADS_PACK = MetaAdsPack(), GoogleAdsPack()
