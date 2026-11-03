# Razorpay pack

Tables (dashboard exports: rupees, IST; API/CLI JSON: paise → rupees, unix → TIMESTAMPTZ — both normalized):
- `orders` id, amount, amount_paid, amount_due, currency, receipt, status (created | attempted | paid), attempts, created_at
- `payments` id, amount, currency, status (created | authorized | captured | refunded | failed), order_id (NULL for
  payment links / QR / bank transfer), method, captured, amount_refunded, fee, tax, error_code, error_description, created_at
- `refunds` id, amount, payment_id, created_at · `settlements` id, amount, fees, tax, utr
- `combined` one row per ledger entity: entity_id, type (payment | refund | settlement | adjustment …), debit, credit,
  settled, settlement_id · `settlement_recon` per-transaction settlement detail · `subscriptions`

Live data without the dashboard: `razorpay payments list --count 100 --skip 0 > data/payments_0.json` (Razorpay CLI,
user's own keys in ~/.razorpay; the API caps a page at 100 — confirm paging flags with
`razorpay payments list --help`), then `databook import data/payments_*.json`.

Funnel definitions (template `razorpay-funnel` implements them):
created = all orders · attempted = status ∈ {attempted, paid} or attempts > 0 · paid = status 'paid' ·
captured = order has ≥1 captured payment · settled = a captured payment of the order is in `combined` with settled.
Count orders, never payment rows (an order can have several attempts). Payments with NULL order_id are outside the
order funnel — report them separately. Revenue lost = sum(amount) of orders with status 'attempted'.
Refunded payments keep captured = true; subtract refunds explicitly for net figures.
