---
title: Customer dashboard
params:
  customer: { from: customer_list.customer_id, show: customer_list.label, default: 16029, label: Customer }
---
# Customer at a glance

Pick a customer to see how much they buy, how often, what they buy, and whether they are slipping away. All money is in
pounds sterling (£).

```sql settings "Status rules"
SELECT 14 AS min_gap_days,    -- customers who order very often are judged against at least this gap
       2 AS active_within,    -- Active: last order within this many usual gaps
       4 AS slipping_within   -- Slipping: within this many usual gaps; beyond that, Lapsed
```

```sql lines "All order lines, both sheets, overlap removed"
SELECT * FROM online_retail_ii_year_2009_2010
WHERE invoicedate < TIMESTAMP '2010-12-01'  -- 1–9 Dec 2010 is in both sheets; keep the second sheet's copy
UNION ALL
SELECT * FROM online_retail_ii_year_2010_2011
```

```sql product_lines "Product sales and cancellations of known customers"
SELECT invoice, stockcode, description, quantity, price, customer_id, country, invoicedate,
       quantity * price AS amount,
       CASE WHEN invoice LIKE 'C%' THEN 'cancellation' ELSE 'sale' END AS kind
FROM lines
WHERE customer_id IS NOT NULL
  AND (invoice LIKE 'C%' OR (quantity > 0 AND price > 0 AND invoice NOT LIKE 'A%'))
  AND stockcode NOT IN ('POST', 'DOT', 'C2', 'AMAZONFEE', 'BANK CHARGES', 'CRUK', 'M', 'm', 'D', 'S',
                        'ADJUST', 'ADJUST2', 'B', 'TEST001', 'TEST002', 'C3', 'GIFT')
```

```sql data_end "Last day of data"
SELECT max(invoicedate)::DATE AS day FROM lines
```

```sql orders "One row per invoice"
SELECT customer_id, invoice, kind,
       min(invoicedate) AS ordered_at,
       min(invoicedate)::DATE AS day,
       count(*) AS lines,
       sum(amount) AS amount
FROM product_lines
GROUP BY customer_id, invoice, kind
```

```sql gaps "Days between a customer's order days"
SELECT customer_id, day - lag(day) OVER (PARTITION BY customer_id ORDER BY day) AS gap_days
FROM (SELECT DISTINCT customer_id, day FROM orders WHERE kind = 'sale')
```

```sql customers "One row per customer"
WITH s AS (
  SELECT customer_id,
         count(*) FILTER (WHERE kind = 'sale') AS orders,
         min(day) FILTER (WHERE kind = 'sale') AS first_order,
         max(day) FILTER (WHERE kind = 'sale') AS last_order,
         sum(amount) FILTER (WHERE kind = 'sale') AS gross_spend,
         coalesce(sum(amount) FILTER (WHERE kind = 'cancellation'), 0) AS cancelled,
         count(*) FILTER (WHERE kind = 'cancellation') AS cancellations
  FROM orders GROUP BY customer_id
), g AS (
  SELECT customer_id, median(gap_days) AS usual_gap FROM gaps WHERE gap_days IS NOT NULL GROUP BY customer_id
), c AS (
  SELECT customer_id, arg_max(country, invoicedate) AS country FROM product_lines GROUP BY customer_id
)
SELECT s.customer_id, c.country, s.orders, s.first_order, s.last_order,
       s.gross_spend + s.cancelled AS net_spend,
       s.gross_spend / s.orders AS avg_order,
       s.cancellations, -s.cancelled AS cancelled_value,
       g.usual_gap,
       e.day - s.last_order AS days_since,
       CASE
         WHEN s.orders = 1 THEN 'One-time buyer'
         WHEN days_since <= st.active_within * greatest(g.usual_gap, st.min_gap_days) THEN 'Active'
         WHEN days_since <= st.slipping_within * greatest(g.usual_gap, st.min_gap_days) THEN 'Slipping'
         ELSE 'Lapsed'
       END AS status
FROM s
JOIN c ON c.customer_id = s.customer_id
LEFT JOIN g ON g.customer_id = s.customer_id
CROSS JOIN settings st
CROSS JOIN data_end e
WHERE s.orders > 0
```

```sql customer_list "Customers to pick from, biggest spenders first"
SELECT customer_id,
       customer_id::VARCHAR || ' · ' || country || ' · ' || status || ' · £' || round(net_spend)::BIGINT AS label
FROM customers
```

## Who is this?

```sql me "The picked customer"
SELECT * FROM customers WHERE customer_id = $customer
```

```sql me_since "When they last ordered compared with their usual gap"
SELECT days_since,
       usual_gap,
       CASE WHEN usual_gap > 0 THEN days_since / usual_gap END AS gaps_missed,
       CASE WHEN orders = 1 THEN 'That was their only order.'
            WHEN days_since <= usual_gap THEN 'They usually order every ' || round(usual_gap, 1) || ' days, so they are on track.'
            ELSE 'They usually order every ' || round(usual_gap, 1) || ' days, so that is '
                 || round(gaps_missed, 1) || ' usual gaps.' END AS cadence
FROM me
```

Customer **{{me.customer_id | text}}** from {{me.country | text}} is **{{me.status | text}}**. They first ordered on
{{me.first_order | date}} and last ordered on {{me.last_order | date}}, {{me.days_since | int}} days before the data
ends. {{me_since.cadence | text}}

```kpi
- { label: Net spend (£), value: me.net_spend, format: gbp }
- { label: Orders, value: me.orders, format: int }
- { label: Average order (£), value: me.avg_order, format: gbp }
- { label: Days since last order, value: me.days_since, format: int }
- { label: Usual days between orders, value: me.usual_gap, format: num }
```

## How has their spending changed?

```sql months "Every month in the data"
SELECT unnest(generate_series(DATE '2009-12-01', date_trunc('month', (SELECT day FROM data_end))::DATE,
                              INTERVAL 1 MONTH))::DATE AS month
```

```sql me_monthly "Monthly net spend"
SELECT m.month, coalesce(sum(o.amount), 0) AS net_spend
FROM months m
LEFT JOIN orders o ON o.customer_id = $customer AND date_trunc('month', o.day) = m.month
GROUP BY m.month
ORDER BY m.month
```

```chart
{ type: bar, data: me_monthly, x: month, y: net_spend, format: gbp, title: Net spend by month,
  description: Sales minus cancellations; the last month is partial }
```

## What do they buy?

```sql me_products "Top products by spend"
SELECT stockcode, any_value(description) AS product,
       sum(quantity) FILTER (WHERE kind = 'sale') AS units,
       sum(amount) AS net_spend
FROM product_lines
WHERE customer_id = $customer
GROUP BY stockcode
ORDER BY net_spend DESC, stockcode
LIMIT 10
```

```table
{ data: me_products, columns: [product, units, net_spend], format: { net_spend: gbp } }
```

## Recent orders

```sql me_orders "Last 10 invoices"
SELECT day, invoice, CASE WHEN kind = 'sale' THEN 'Order' ELSE 'Cancellation' END AS type, lines, amount
FROM orders
WHERE customer_id = $customer
ORDER BY ordered_at DESC, invoice
LIMIT 10
```

```table
{ data: me_orders, columns: [day, invoice, type, lines, amount], format: { day: date, amount: gbp } }
```

They cancelled {{me.cancellations | int}} invoice(s), worth {{me.cancelled_value | gbp}} in total.

## Customers to call this week

Regular customers who are slipping: they have gone longer than usual without ordering but have not lapsed yet. Click a
customer to open their page.

```sql slipping "Slipping customers, biggest spenders first"
SELECT customer_id, country, orders, net_spend, usual_gap, days_since
FROM customers
WHERE status = 'Slipping' AND orders >= 5
ORDER BY net_spend DESC, customer_id
LIMIT 15
```

```table
{ data: slipping, columns: [customer_id, country, orders, net_spend, usual_gap, days_since],
  format: { net_spend: gbp, usual_gap: num, days_since: int }, link: { column: customer_id, param: customer } }
```

## Notes

- Data: Online Retail II (UCI), every invoice of a UK online gift wholesaler from Dec 2009 to {{data_end.day | date}}.
  Only invoices with a customer id are used; postage, fees, manual adjustments and test lines are left out.
- Net spend is product sales minus cancellations. Usual gap is the median number of days between a customer's order
  days.
- Status: **Active** if the last order was within {{settings.active_within | int}} usual gaps, **Slipping** within
  {{settings.slipping_within | int}}, otherwise **Lapsed**; very frequent buyers are judged against a gap of at least
  {{settings.min_gap_days | int}} days. Change the rules in the first block.
