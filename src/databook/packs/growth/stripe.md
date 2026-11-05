# Stripe pack

Get data, either:
- Dashboard → Payments → Export (all columns) → unified_payments.csv → table `stripe_payments`: major units,
  `created_date_utc` (UTC), status Paid | Refunded | Partially refunded | Failed | Uncaptured, `converted_amount` in
  the account's settlement currency (use it to sum across currencies). Metadata columns arrive as `<key>_metadata`.
- Stripe CLI (user's own login, `stripe login`): `stripe charges list --limit 100 > data/stripe_charges.json`; page
  with `--starting-after <last id>` while has_more is true (one file per page is fine). Same for `customers`,
  `subscriptions` (add `--status all` or canceled ones are omitted), `invoices`, `refunds`, `payment_intents`.
  Recognized by each item's `object` → tables stripe_charges, stripe_customers, stripe_subscriptions, stripe_invoices,
  stripe_refunds, stripe_payment_intents. Amounts are integer minor units → converted with the row's currency
  (JPY etc. exact); unix seconds → TIMESTAMPTZ; nested objects (metadata, items, billing_details) stay JSON text.

Revenue: charges with status 'succeeded' (CLI) / 'Paid'+'Refunded'+'Partially refunded' (export) minus amount_refunded.
Fees are only in the export (`fee`) or balance_transactions. MRR from subscriptions (status active / past_due; nested
prices are still MINOR units — divide by 100, or 1 for zero-decimal currencies):
```sql
SELECT s.id, sum(CAST(i.price.unit_amount AS DECIMAL(18,2)) / 100 * i.quantity / coalesce(i.price.recurring.interval_count, 1)
        * CASE i.price.recurring.interval WHEN 'year' THEN 1/12 WHEN 'week' THEN 52/12 WHEN 'day' THEN 365/12 ELSE 1 END) AS mrr
FROM stripe_subscriptions s, unnest(from_json(s.items->'$.data', '[{"quantity":"BIGINT","price":{"unit_amount":"BIGINT",
     "recurring":{"interval":"VARCHAR","interval_count":"BIGINT"}}}]')) AS u(i)
WHERE s.status IN ('active', 'past_due') GROUP BY ALL
```
Churned = canceled_at in period. Ignores discounts/coupons; say so when reporting MRR.
