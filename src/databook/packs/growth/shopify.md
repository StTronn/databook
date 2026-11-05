# Shopify pack

Get data: Shopify admin → Orders → Export → "All orders" (or a date range) → "CSV for Excel…" (plain CSV). Big
exports arrive as orders_export_1.csv, _2 … — import them together: `databook import data/orders_export_*.csv`.
Never import overlapping date ranges (no row key; the import warns on identical rows across files).

Table `shopify_order_lines` — ONE ROW PER LINE ITEM. Order-level columns (financial_status, paid_at, currency,
subtotal, shipping, taxes, total, discount_*, refunded_amount, tags, source …) are filled on the order's FIRST line
only, NULL on the rest. `name` (#1001) and `id` are on every line. Timestamps keep the store's UTC offset → TIMESTAMPTZ.
financial_status: pending | authorized | paid | partially_paid | partially_refunded | refunded | voided.

Orders (always roll up before counting or summing money — summing `total` per line is wrong only by luck):
```sql
SELECT name AS order_name, min(created_at) AS created_at, max(email) AS email, max(financial_status) AS financial_status,
       max(total) AS total, coalesce(max(refunded_amount), 0) AS refunded, max(cancelled_at) AS cancelled_at,
       max(discount_code) AS discount_code, max(source) AS source, sum(lineitem_quantity) AS units
FROM shopify_order_lines GROUP BY name
```
Net revenue = total − refunded over orders with cancelled_at IS NULL. Customer key = lower(email) (guest checkouts
have no customer id in the export); first order: `row_number() OVER (PARTITION BY lower(email) ORDER BY created_at) = 1`.
Join to Stripe/GA4 by order name only if the store writes it there (Stripe description "Order #1001", GA4 transaction_id).
