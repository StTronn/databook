"""Growth source packs (shopify, stripe, ga4, meta_ads, google_ads) on hand-built fixtures in each vendor's export shape."""
import json
from datetime import date, datetime, timezone
from decimal import Decimal

from conftest import FIX
from databook.cli import main
from databook.ingest import types as T

G = FIX / "growth"
UTC = timezone.utc


def _one(con, sql):
    return con.execute(sql).fetchone()


def test_all_growth_fixtures_route_to_their_packs(project, capsys):
    files = [str(G / f) for f in ("shopify_orders_export_1.csv", "stripe_unified_payments.csv", "stripe_charges.json",
                                  "stripe_subscriptions.json", "ga4_events_20240115.jsonl", "meta_ads_export.csv",
                                  "google_ads_campaign_report.csv")]
    assert main(["import", *files]) == 0
    assert {k: v["source"] for k, v in project.manifest["tables"].items()} == {
        "shopify_order_lines": "shopify.orders", "stripe_payments": "stripe.payments", "stripe_charges": "stripe.charges",
        "stripe_subscriptions": "stripe.subscriptions", "ga4_events": "ga4.events", "meta_ads": "meta_ads.insights",
        "google_ads": "google_ads.report"}
    out = capsys.readouterr().out
    assert "dropped 1 'Total:' summary row(s)" in out
    con = project.connect(read_only=True)

    # Shopify: line rows kept (no dedup on repeated order id), offset timestamps exact, zips stay text
    assert _one(con, "SELECT count(*), count(DISTINCT name) FROM shopify_order_lines") == (3, 2)
    assert _one(con, "SELECT created_at, billing_zip, total, accepts_marketing FROM shopify_order_lines "
                     "WHERE financial_status = 'paid'") == (datetime(2024, 1, 15, 15, 23, 45, tzinfo=UTC), "02134",
                                                            Decimal("81.30"), True)
    assert _one(con, "SELECT sum(t) FROM (SELECT max(total) t FROM shopify_order_lines GROUP BY name)")[0] == Decimal("121.30")

    # Stripe export: naive UTC column, major units; zero-decimal JPY stays 1000
    assert _one(con, "SELECT created_date_utc, amount, fee FROM stripe_payments WHERE id = 'ch_3OaA1'") == \
        (datetime(2024, 1, 15, 15, 23, 45, tzinfo=UTC), Decimal("81.30"), Decimal("2.66"))
    assert _one(con, "SELECT amount FROM stripe_payments WHERE currency = 'jpy'")[0] == Decimal("1000.00")
    # Stripe API: `object` routes, minor units by currency (usd ÷100, jpy ÷1), unix seconds
    assert con.execute("SELECT id, amount, created FROM stripe_charges ORDER BY id").fetchall() == [
        ("ch_1", Decimal("81.30"), datetime(2024, 1, 15, 15, 23, 45, tzinfo=UTC)),
        ("ch_2", Decimal("1000.00"), datetime(2024, 2, 2, 8, 0, tzinfo=UTC))]
    assert _one(con, "SELECT canceled_at FROM stripe_subscriptions WHERE id = 'sub_2'")[0] == datetime(2024, 2, 1, tzinfo=UTC)
    assert json.loads(_one(con, "SELECT items FROM stripe_subscriptions WHERE id = 'sub_1'")[0])["object"] == "list"

    # GA4: one row per event (rows' own `items` arrays are not unwrapped), µs timestamps exact, ids stay text
    assert _one(con, "SELECT count(*) FROM ga4_events")[0] == 3
    assert _one(con, "SELECT event_date, event_timestamp, user_pseudo_id, stream_id FROM ga4_events "
                     "WHERE event_name = 'session_start'") == (date(2024, 1, 15), datetime(2024, 1, 15, 15, 20, 0, 1, tzinfo=UTC),
                                                               "1234567890.1705332000", "4567890123")

    # Meta: currency stripped from headers into a column; Google: preamble skipped, totals dropped, "--" → NULL
    assert _one(con, "SELECT sum(amount_spent), any_value(currency) FROM meta_ads") == (Decimal("213.55"), "USD")
    assert "cpm_cost_per_1_000_impressions" in [r[0] for r in con.execute("DESCRIBE meta_ads").fetchall()]
    assert con.execute("SELECT day, cost, impr, conv_rate FROM google_ads ORDER BY day").fetchall() == [
        (datetime(2024, 1, 15), Decimal("1204.50"), 12034, "3.05%"), (datetime(2024, 1, 16), Decimal("98.10"), 1500, None)]


def test_google_ads_utf16_excel_csv_and_overlap_warning(project, capsys):
    assert main(["import", str(G / "google_ads_campaign_report_excel.csv")]) == 0
    con = project.connect(read_only=True)
    assert _one(con, "SELECT count(*), sum(cost) FROM google_ads") == (2, Decimal("1302.60"))
    con.close()
    capsys.readouterr()
    assert main(["import", str(G / "google_ads_campaign_report.csv"), str(G / "google_ads_campaign_report_excel.csv")]) == 0
    assert "2 row(s) identical to rows of another file in google_ads" in capsys.readouterr().out


def test_razorpay_and_stripe_json_do_not_collide(project, tmp_path):
    (tmp_path / "rzp.json").write_text(json.dumps({"entity": "collection", "count": 1, "items": [
        {"id": "rfnd_1", "entity": "refund", "amount": 500, "currency": "INR", "payment_id": "pay_1", "created_at": 1700000000}]}))
    (tmp_path / "str.json").write_text(json.dumps({"object": "list", "data": [
        {"id": "re_1", "object": "refund", "amount": 500, "currency": "usd", "charge": "ch_1", "created": 1700000000}]}))
    assert main(["import", str(tmp_path / "rzp.json"), str(tmp_path / "str.json")]) == 0
    m = project.manifest["tables"]
    assert m["refunds"]["source"] == "razorpay.refunds" and m["stripe_refunds"]["source"] == "stripe.refunds"


def test_new_converters():
    assert T.conv_unix_us("1705332000000001", None) == "2024-01-15 15:20:00.000001+00:00"
    assert T.conv_yyyymmdd("20240229", None) == "2024-02-29"
    assert T.conv_utc("2024-01-15 15:23:45", None) == "2024-01-15 15:23:45+00:00"
    assert T._parse_dt("2024-01-15 10:23:45 -0500", None)[0].utcoffset().total_seconds() == -5 * 3600
    assert T.infer(["2024-01-15 10:23:45 -0500"])[0] == "tz_timestamp"
    for bad, fn in (("2024-13-01", T.conv_yyyymmdd), ("2024011", T.conv_yyyymmdd), ("1.5", T.conv_unix_us)):
        try:
            fn(bad, None)
            raise AssertionError(bad)
        except ValueError:
            pass
