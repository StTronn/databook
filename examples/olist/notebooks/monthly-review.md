---
title: Monthly business review — August 2018
---
# Monthly business review — August 2018

How the marketplace did in August 2018, the last complete month, compared with July 2018 and August 2017. All money is in Brazilian reais (R$).

```sql deliv "Delivered orders, one row per order"
WITH items AS (
  SELECT order_id, sum(price) AS revenue, sum(freight_value) AS freight, count(*) AS items
  FROM order_items GROUP BY order_id
), pays AS (
  SELECT order_id, sum(payment_value) AS payments
  FROM order_payments GROUP BY order_id
)
SELECT o.order_id,
       date_trunc('month', o.order_purchase_timestamp)::DATE AS month,
       c.customer_unique_id, c.customer_state, c.customer_city,
       i.revenue, i.freight, i.items, p.payments
FROM orders o
JOIN customers c ON c.customer_id = o.customer_id
JOIN items i ON i.order_id = o.order_id
LEFT JOIN pays p ON p.order_id = o.order_id
WHERE o.order_status = 'delivered'
```

```sql monthly "Monthly KPIs"
SELECT month,
       sum(revenue) AS revenue,
       count(*) AS orders,
       count(DISTINCT customer_unique_id) AS customers,
       sum(revenue) / count(*) AS aov
FROM deliv
GROUP BY month
ORDER BY month
```

```sql aug18
SELECT * FROM monthly WHERE month = DATE '2018-08-01'
```

```sql jul18
SELECT * FROM monthly WHERE month = DATE '2018-07-01'
```

```sql aug17
SELECT * FROM monthly WHERE month = DATE '2017-08-01'
```

**August 2018 vs July 2018**

```kpi
- { label: Revenue (R$), value: aug18.revenue, format: num, compare: jul18.revenue }
- { label: Delivered orders, value: aug18.orders, format: int, compare: jul18.orders }
- { label: Customers, value: aug18.customers, format: int, compare: jul18.customers }
- { label: AOV (R$), value: aug18.aov, format: num, compare: jul18.aov }
```

**August 2018 vs August 2017**

```kpi
- { label: Revenue (R$), value: aug18.revenue, format: num, compare: aug17.revenue }
- { label: Delivered orders, value: aug18.orders, format: int, compare: aug17.orders }
- { label: Customers, value: aug18.customers, format: int, compare: aug17.customers }
- { label: AOV (R$), value: aug18.aov, format: num, compare: aug17.aov }
```

```sql cat_month "Category revenue, July and August 2018"
SELECT coalesce(t.product_category_name_english, p.product_category_name, '(no category)') AS category,
       sum(i.price) FILTER (WHERE d.month = DATE '2018-07-01') AS jul_revenue,
       sum(i.price) FILTER (WHERE d.month = DATE '2018-08-01') AS aug_revenue
FROM deliv d
JOIN order_items i ON i.order_id = d.order_id
JOIN products p ON p.product_id = i.product_id
LEFT JOIN product_category_name_translation t ON t.product_category_name = p.product_category_name
WHERE d.month IN (DATE '2018-07-01', DATE '2018-08-01')
GROUP BY 1
```

```sql drivers "What drove August"
WITH biggest_drop AS (
  SELECT category, coalesce(aug_revenue, 0) - coalesce(jul_revenue, 0) AS change
  FROM cat_month ORDER BY change ASC LIMIT 1
), biggest_gain AS (
  SELECT category, coalesce(aug_revenue, 0) - coalesce(jul_revenue, 0) AS change
  FROM cat_month ORDER BY change DESC LIMIT 1
)
SELECT a.revenue / j.revenue - 1 AS revenue_mom,
       a.orders / j.orders - 1 AS orders_mom,
       a.aov / j.aov - 1 AS aov_mom,
       a.revenue / y.revenue - 1 AS revenue_yoy,
       d.category AS drop_category, -d.change AS drop_amount,
       g.category AS gain_category, g.change AS gain_amount
FROM aug18 a, jul18 j, aug17 y, biggest_drop d, biggest_gain g
```

**What drove the month:** delivered orders rose {{drivers.orders_mom | pct}} on July, but the average order was {{drivers.aov_mom | pct}} smaller, so revenue changed by {{drivers.revenue_mom | pct}} — mostly because {{drivers.drop_category | text}} fell by R$ {{drivers.drop_amount | num}} (partly offset by {{drivers.gain_category | text}}, up R$ {{drivers.gain_amount | num}}). Against August 2017, revenue is up {{drivers.revenue_yoy | pct}}.

## 1. How are sales trending?

```sql trend "Revenue and delivered orders, Jan 2017 – Aug 2018"
SELECT strftime(month, '%Y-%m') AS month, revenue, orders
FROM monthly
WHERE month BETWEEN DATE '2017-01-01' AND DATE '2018-08-01'
ORDER BY month
```

```sql trend_peak
SELECT arg_max(month, revenue) AS peak_month, max(revenue) AS peak_revenue
FROM trend
```

Revenue climbed through 2017 and peaked in {{trend_peak.peak_month | text}} (the Black Friday month) at R$ {{trend_peak.peak_revenue | num}}. In 2018 it has levelled off, easing slightly since May, with delivered orders following the same shape.

```chart
{ type: bar, data: trend, x: month, y: revenue, format: num, title: "Revenue by purchase month (R$)" }
```

```chart
{ type: line, data: trend, x: month, y: orders, variant: dots, format: int, title: "Delivered orders by purchase month" }
```

## 2. What's selling?

```sql cat12 "Revenue by category, Sep 2017 – Aug 2018"
SELECT coalesce(t.product_category_name_english, p.product_category_name, '(no category)') AS category,
       sum(i.price) AS revenue
FROM deliv d
JOIN order_items i ON i.order_id = d.order_id
JOIN products p ON p.product_id = i.product_id
LEFT JOIN product_category_name_translation t ON t.product_category_name = p.product_category_name
WHERE d.month BETWEEN DATE '2017-09-01' AND DATE '2018-08-01'
GROUP BY 1
```

```sql top_cats "Top 10 categories by revenue, Sep 2017 – Aug 2018"
SELECT category, revenue, revenue / (SELECT sum(revenue) FROM cat12) AS share
FROM cat12
ORDER BY revenue DESC
LIMIT 10
```

```sql top_cats_sum
SELECT sum(share) AS top10_share, arg_max(category, revenue) AS top_category, max(share) AS top_share
FROM top_cats
```

The top 10 categories brought in {{top_cats_sum.top10_share | pct}} of revenue over the last 12 months; {{top_cats_sum.top_category | text}} leads with {{top_cats_sum.top_share | pct}}.

```chart
{ type: bar, data: top_cats, x: category, y: revenue, variant: horizontal, format: num, title: "Top 10 categories by revenue (R$), Sep 2017 – Aug 2018" }
```

```table
{ data: top_cats, columns: [category, revenue, share], sort: revenue desc, format: { revenue: num, share: pct } }
```

## 3. Where are our customers?

```sql by_state "Revenue by customer state, Sep 2017 – Aug 2018"
SELECT customer_state AS state,
       sum(revenue) AS revenue,
       sum(revenue) / sum(sum(revenue)) OVER () AS share,
       count(*) AS orders,
       count(DISTINCT customer_unique_id) AS customers
FROM deliv
WHERE month BETWEEN DATE '2017-09-01' AND DATE '2018-08-01'
GROUP BY 1
ORDER BY revenue DESC
```

```sql state_top
SELECT arg_max(state, revenue) AS top_state, max(share) AS top_share, count(*) AS states
FROM by_state
```

{{state_top.top_state | text}} alone accounts for {{state_top.top_share | pct}} of revenue across {{state_top.states | int}} states.

```chart
{ type: bar, data: by_state, x: state, y: revenue, format: num, title: "Revenue by state (R$), Sep 2017 – Aug 2018" }
```

```table
{ data: by_state, columns: [state, revenue, share, orders, customers], sort: revenue desc, format: { revenue: num, share: pct, orders: int, customers: int } }
```

```sql low_cities "Five cities with the lowest total payments, Sep 2017 – Aug 2018"
WITH c AS (
  SELECT customer_city AS city, customer_state AS state,
         sum(payments) AS total_payments, count(*) AS orders
  FROM deliv
  WHERE month BETWEEN DATE '2017-09-01' AND DATE '2018-08-01' AND payments IS NOT NULL
  GROUP BY 1, 2
)
SELECT city, state, total_payments, orders
FROM c
QUALIFY rank() OVER (ORDER BY total_payments ASC) <= 5
ORDER BY total_payments
```

Cities are told apart by state, since the same name exists in several states. Each of the lowest five placed a single small order.

```table
{ data: low_cities, columns: [city, state, total_payments, orders], sort: total_payments asc, format: { total_payments: num, orders: int } }
```

## 4. Who are our best customers?

```sql top_by_orders "Top customers by delivered orders (ties included), Sep 2017 – Aug 2018"
WITH c AS (
  SELECT customer_unique_id AS customer, count(*) AS delivered_orders, sum(revenue) AS revenue
  FROM deliv
  WHERE month BETWEEN DATE '2017-09-01' AND DATE '2018-08-01'
  GROUP BY 1
)
SELECT rank() OVER (ORDER BY delivered_orders DESC) AS rank, customer, delivered_orders, revenue
FROM c
QUALIFY rank() OVER (ORDER BY delivered_orders DESC) <= 10
ORDER BY delivered_orders DESC, customer
```

```sql repeat
SELECT count(*) FILTER (WHERE n >= 2) / count(*) AS repeat_share
FROM (SELECT customer_unique_id, count(*) AS n FROM deliv
      WHERE month BETWEEN DATE '2017-09-01' AND DATE '2018-08-01' GROUP BY 1)
```

Repeat buying is rare: only {{repeat.repeat_share | pct}} of customers had two or more delivered orders in the last 12 months. The top 10 by order count (including everyone tied at 10th place):

```table
{ data: top_by_orders, columns: [rank, customer, delivered_orders, revenue], format: { rank: int, delivered_orders: int, revenue: num } }
```

```sql top_by_avg "Top 10 customers by average payment per order, Sep 2017 – Aug 2018"
WITH c AS (
  SELECT customer_unique_id AS customer, count(*) AS delivered_orders,
         sum(payments) AS total_payments, avg(payments) AS avg_payment
  FROM deliv
  WHERE month BETWEEN DATE '2017-09-01' AND DATE '2018-08-01' AND payments IS NOT NULL
  GROUP BY 1
)
SELECT rank() OVER (ORDER BY avg_payment DESC) AS rank, customer, avg_payment, delivered_orders, total_payments
FROM c
QUALIFY rank() OVER (ORDER BY avg_payment DESC) <= 10
ORDER BY avg_payment DESC
```

By average payment per order, the top customers are one-off big purchases:

```table
{ data: top_by_avg, columns: [rank, customer, avg_payment, delivered_orders, total_payments], format: { rank: int, avg_payment: num, delivered_orders: int, total_payments: num } }
```

## 5. How do customers pay?

```sql pay_mix "Payment mix, delivered orders Sep 2017 – Aug 2018"
SELECT p.payment_type,
       sum(p.payment_value) AS payment_value,
       sum(p.payment_value) / sum(sum(p.payment_value)) OVER () AS value_share,
       count(DISTINCT p.order_id) AS orders_using
FROM order_payments p
JOIN deliv d ON d.order_id = p.order_id
WHERE d.month BETWEEN DATE '2017-09-01' AND DATE '2018-08-01'
GROUP BY 1
ORDER BY payment_value DESC
```

```sql pay_top
SELECT arg_max(payment_type, payment_value) AS top_type, max(value_share) AS top_share
FROM pay_mix
```

{{pay_top.top_type | text}} carries {{pay_top.top_share | pct}} of the money paid. An order can use more than one method (e.g. voucher plus card), so orders by method add up to more than total orders.

```chart
{ type: pie, data: pay_mix, x: payment_type, y: payment_value, variant: donut, format: num, title: "Share of payment value by method" }
```

```table
{ data: pay_mix, columns: [payment_type, payment_value, value_share, orders_using], format: { payment_value: num, value_share: pct, orders_using: int } }
```

## Notes

- **Customer** = `customer_unique_id` (one person can have several `customer_id`s, one per order).
- **Orders**: only orders with status *delivered* are counted, everywhere in this report.
- **Revenue** = sum of item `price`, in R$, assigned to the month the order was purchased. Freight is excluded. **AOV** = revenue ÷ delivered orders.
- **Payments** (sections 3–5) = `payment_value`, which includes freight and is what the customer actually paid.
- Sections 3–5 cover the same 12 months as section 2: September 2017 to August 2018.
- Categories without an English name are shown under their Portuguese name; products with no category are shown as "(no category)".
- **September and October 2018 are incomplete** (a handful of orders, none yet delivered), so August 2018 is the last complete month and they are left out.
- Source: `data/olist.sqlite`, September 2016 to October 2018.
