---
title: Razorpay checkout funnel
description: From order to settlement, built from Razorpay dashboard exports.
---
# Checkout funnel

Of {{funnel.created | int}} orders, {{funnel.paid | int}} were paid: a conversion of **{{funnel.conv_paid | pct}}**.
Orders that tried to pay and never did are worth **{{lost.inr | inr}}**.

```sql funnel "Funnel counts"
WITH pay AS (
  SELECT order_id, bool_or(captured) AS captured
  FROM payments WHERE order_id IS NOT NULL GROUP BY order_id
), settled AS (
  SELECT DISTINCT p.order_id
  FROM combined c JOIN payments p ON p.id = c.entity_id
  WHERE c.type = 'payment' AND c.settled AND p.order_id IS NOT NULL
)
SELECT
  count(*)                                                                    AS created,
  count(*) FILTER (WHERE o.status IN ('attempted', 'paid') OR o.attempts > 0) AS attempted,
  count(*) FILTER (WHERE o.status = 'paid')                                   AS paid,
  count(*) FILTER (WHERE pay.captured)                                        AS captured,
  count(*) FILTER (WHERE o.id IN (SELECT order_id FROM settled))              AS settled,
  paid / created                                                              AS conv_paid
FROM orders o LEFT JOIN pay ON pay.order_id = o.id
WHERE o.currency = 'INR'
```

```sql lost "Unpaid order value"
SELECT coalesce(sum(amount), 0) AS inr, count(*) AS orders
FROM orders WHERE status = 'attempted' AND currency = 'INR'
```

```kpi
- { label: Orders, value: funnel.created, format: int }
- { label: Paid, value: funnel.paid, format: int }
- { label: Conversion, value: funnel.conv_paid, format: pct }
- { label: Lost to failed checkouts, value: lost.inr, format: inr_short }
```

```chart
{ type: radial, data: funnel, y: conv_paid, format: pct, variant: text, title: Paid conversion,
  description: Share of created orders that were paid }
```

```sql funnel_stages "Funnel stages"
SELECT stage, n FROM (
  SELECT 1 AS k, 'Orders created' AS stage, created AS n FROM funnel UNION ALL
  SELECT 2, 'Checkout attempted', attempted FROM funnel UNION ALL
  SELECT 3, 'Paid', paid FROM funnel UNION ALL
  SELECT 4, 'Captured', captured FROM funnel UNION ALL
  SELECT 5, 'Settled', settled FROM funnel
) ORDER BY k
```

```chart
{ type: funnel, data: funnel_stages, x: stage, y: n, title: Orders by stage }
```

## Where payments fail

Success rate by payment method, and the value of unpaid orders whose last attempt used that method.

```sql methods "Payment methods"
WITH last_try AS (
  SELECT order_id, arg_max(method, created_at) AS method
  FROM payments WHERE order_id IS NOT NULL GROUP BY order_id
), lost AS (
  SELECT l.method, sum(o.amount) AS lost_inr, count(*) AS lost_orders
  FROM orders o JOIN last_try l ON l.order_id = o.id
  WHERE o.status <> 'paid' GROUP BY l.method
)
SELECT p.method,
       count(*)                                 AS payments,
       count(*) FILTER (WHERE p.captured)       AS succeeded,
       succeeded / payments                     AS success_rate,
       coalesce(any_value(lost.lost_orders), 0) AS lost_orders,
       coalesce(any_value(lost.lost_inr), 0)    AS lost_inr
FROM payments p LEFT JOIN lost ON lost.method = p.method
WHERE p.order_id IS NOT NULL
GROUP BY p.method
ORDER BY lost_inr DESC
```

```chart
{ type: bar, data: methods, x: method, y: [payments, succeeded], title: Attempts vs successes,
  description: Payments per method }
```

```chart
{ type: pie, data: methods, x: method, y: lost_inr, format: inr, variant: donut-text,
  title: Unpaid value by last method tried }
```

```table
{ data: methods, columns: [method, payments, succeeded, success_rate, lost_orders, lost_inr],
  format: { success_rate: pct, lost_inr: inr } }
```

```sql failures "Failure reasons"
SELECT method || ' · ' || error_description AS reason, count(*) AS failed_payments
FROM payments WHERE NOT captured AND order_id IS NOT NULL
GROUP BY ALL ORDER BY failed_payments DESC LIMIT 8
```

```chart
{ type: hbar, data: failures, x: reason, y: failed_payments, title: Top failure reasons }
```

## Week by week

```python weekly "Weekly orders"
local = orders["created_at"].dt.tz_convert(TZ)
week = (local.dt.normalize() - pd.to_timedelta(local.dt.day_of_week, unit="D")).dt.date
df = pd.DataFrame({"week": week, "paid": orders["status"].eq("paid")})
out = df.groupby("week").agg(orders=("paid", "size"), paid=("paid", "sum")).reset_index()
out["conversion"] = out["paid"] / out["orders"]
return out
```

```chart
{ type: combo, data: weekly, x: week, title: Orders and paid orders by week,
  y: [{col: orders, mark: bar, label: Orders}, {col: paid, mark: line, label: Paid}] }
```

```chart
{ type: line, data: weekly, x: week, y: conversion, format: pct, variant: dots,
  title: Paid conversion by week, description: Weeks start on Monday }
```

## What if card payments succeeded more often?

```sql card "Card payments"
SELECT payments, success_rate FROM methods WHERE method = 'card'
```

```sql aov "Average paid order"
SELECT avg(amount) AS inr FROM orders WHERE status = 'paid' AND currency = 'INR'
```

```sheet whatif "Card success what-if"
file: models/whatif.xlsx
inputs:
  Inputs!B2: card.payments
  Inputs!B3: card.success_rate
  Inputs!B5: aov.inr
outputs:
  Model!B4: target
  Model!B5: extra_payments
  Model!B7: uplift_inr
show: Model!A1:B7
```

Raising card success from {{card.success_rate | pct}} to {{whatif.target | pct}} would add about
{{whatif.extra_payments | int}} successful payments, worth an estimated **{{whatif.uplift_inr | inr}}** a month.
