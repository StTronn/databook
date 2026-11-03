---
title: Online store — customer insights 2009–2011
---
# Online store — customer insights, Dec 2009 – Dec 2011

How sales are trending, where revenue comes from, how many customers come back, who the most valuable customers are, and what cancellations cost. All money is in pounds sterling (£).

```sql lines "All order lines, both sheets, overlap removed"
SELECT * FROM online_retail_ii_year_2009_2010
WHERE invoicedate < TIMESTAMP '2010-12-01'  -- 1–9 Dec 2010 is in both sheets; keep the second sheet's copy
UNION ALL
SELECT * FROM online_retail_ii_year_2010_2011
```

```sql items "Order lines, classified"
SELECT
  invoice, stockcode, description, quantity, price, customer_id, country, invoicedate,
  quantity * price AS amount,
  date_trunc('month', invoicedate)::DATE AS month,
  CASE
    WHEN invoice LIKE 'C%' THEN 'cancellation'
    WHEN invoice LIKE 'A%' THEN 'bad_debt'
    WHEN quantity > 0 AND price > 0 THEN 'sale'
    ELSE 'stock_adjustment'
  END AS kind,
  CASE
    WHEN stockcode IN ('POST', 'DOT', 'C2') THEN 'postage'
    WHEN stockcode IN ('AMAZONFEE', 'BANK CHARGES', 'CRUK') THEN 'fees'
    WHEN stockcode IN ('M', 'm', 'D', 'S', 'ADJUST', 'ADJUST2', 'B') THEN 'manual'
    WHEN stockcode IN ('TEST001', 'TEST002', 'C3', 'GIFT') THEN 'test'
    ELSE 'product'
  END AS line_type
FROM lines
```

```sql product_lines "Product sales and product cancellations only"
SELECT * FROM items
WHERE line_type = 'product' AND kind IN ('sale', 'cancellation')
```

## 1. How are revenue and orders trending?

```sql monthly "Monthly sales, cancellations and orders"
SELECT
  strftime(month, '%Y-%m') AS month,
  sum(amount) FILTER (WHERE kind = 'sale') AS gross_sales,
  -coalesce(sum(amount) FILTER (WHERE kind = 'cancellation'), 0) AS cancelled,
  gross_sales - cancelled AS net_sales,
  count(DISTINCT invoice) FILTER (WHERE kind = 'sale') AS orders,
  count(DISTINCT customer_id) FILTER (WHERE kind = 'sale') AS customers,
  gross_sales / orders AS avg_order_value
FROM product_lines
GROUP BY month
ORDER BY month
```

```sql yearly "Last 12 full months vs the 12 before"
SELECT
  sum(net_sales) FILTER (WHERE month BETWEEN '2010-12' AND '2011-11') AS net_sales_y2,
  sum(net_sales) FILTER (WHERE month BETWEEN '2009-12' AND '2010-11') AS net_sales_y1,
  sum(orders)    FILTER (WHERE month BETWEEN '2010-12' AND '2011-11') AS orders_y2,
  sum(orders)    FILTER (WHERE month BETWEEN '2009-12' AND '2010-11') AS orders_y1,
  sum(gross_sales) FILTER (WHERE month BETWEEN '2010-12' AND '2011-11') / orders_y2 AS aov_y2,
  sum(gross_sales) FILTER (WHERE month BETWEEN '2009-12' AND '2010-11') / orders_y1 AS aov_y1,
  net_sales_y2 / net_sales_y1 - 1 AS sales_growth,
  orders_y2 / orders_y1 - 1 AS orders_growth
FROM monthly
```

```sql peak "Best month"
SELECT month, net_sales, orders FROM monthly ORDER BY net_sales DESC LIMIT 1
```

```sql q4_share "Share of yearly sales in Sep–Nov"
SELECT
  sum(net_sales) FILTER (WHERE month BETWEEN '2011-09' AND '2011-11')
    / sum(net_sales) FILTER (WHERE month BETWEEN '2010-12' AND '2011-11') AS autumn_share
FROM monthly
```

```kpi
- { label: "Net sales, Dec 2010–Nov 2011", value: yearly.net_sales_y2, format: gbp_short, compare: yearly.net_sales_y1 }
- { label: "Orders, Dec 2010–Nov 2011", value: yearly.orders_y2, format: int, compare: yearly.orders_y1 }
- { label: "Average order value", value: yearly.aov_y2, format: gbp, compare: yearly.aov_y1 }
```

Over the last 12 full months net sales were **{{yearly.net_sales_y2 | gbp_short}}**, a change of **{{yearly.sales_growth | pct}}** on the 12 months before, while orders changed by **{{yearly.orders_growth | pct}}** — so the business is roughly flat year on year. The pattern is strongly seasonal: sales climb from September and peak in November (best month: **{{peak.month | text}}**, {{peak.net_sales | gbp_short}}); Sep–Nov brings **{{q4_share.autumn_share | pct}}** of the year's sales. December 2011 only covers the 1st–9th, so its dip is not a real drop.

```chart
{ type: combo, data: monthly, x: month, y: [{col: net_sales, mark: bar, label: "Net sales (£)"}, {col: gross_sales, mark: line, label: "Gross sales (£)"}], format: gbp_short, title: "Monthly sales (£)", description: "Gross = all product sales; net = after cancellations and returns. Dec 2011 is a partial month." }
```

```chart
{ type: line, data: monthly, x: month, y: [orders, customers], variant: dots, format: int, title: "Monthly orders and active customers" }
```

## 2. Where does revenue come from?

```sql countries "Net sales by country"
SELECT
  country,
  sum(amount) AS net_sales,
  count(DISTINCT invoice) FILTER (WHERE kind = 'sale') AS orders,
  count(DISTINCT customer_id) FILTER (WHERE kind = 'sale') AS customers,
  sum(amount) / sum(sum(amount)) OVER () AS share
FROM product_lines
GROUP BY country
ORDER BY net_sales DESC
```

```sql top_countries "Top 10 countries plus the rest"
WITH ranked AS (SELECT *, row_number() OVER (ORDER BY net_sales DESC) AS rn FROM countries)
SELECT CASE WHEN rn <= 10 THEN country ELSE 'All other countries' END AS country,
       sum(net_sales) AS net_sales, sum(share) AS share, sum(customers) AS customers, min(rn) AS rn
FROM ranked
GROUP BY 1
ORDER BY rn
```

```sql uk "UK vs international"
SELECT
  sum(share) FILTER (WHERE country = 'United Kingdom') AS uk_share,
  1 - uk_share AS intl_share,
  count(*) AS n_countries,
  max(country) FILTER (WHERE rn = 2) AS second_country,
  max(share) FILTER (WHERE rn = 2) AS second_share
FROM (SELECT *, row_number() OVER (ORDER BY net_sales DESC) AS rn FROM countries)
```

```kpi
- { label: "UK share of net sales", value: uk.uk_share, format: pct }
- { label: "International share", value: uk.intl_share, format: pct }
- { label: "Countries with sales", value: uk.n_countries, format: int }
```

The UK brings in **{{uk.uk_share | pct}}** of net sales. The rest is spread over {{uk.n_countries | int}} countries, led by **{{uk.second_country | text}}** (Ireland) at only {{uk.second_share | pct}} — almost all from a handful of large trade accounts — then the Netherlands, Germany and France.

```chart
{ type: bar, data: top_countries, x: country, y: net_sales, variant: horizontal, format: gbp_short, title: "Net sales by country (£)" }
```

```sql products "Net sales by product"
SELECT
  stockcode,
  mode(description) FILTER (WHERE kind = 'sale') AS description,
  sum(amount) AS net_sales,
  sum(quantity) AS net_units,
  count(DISTINCT invoice) FILTER (WHERE kind = 'sale') AS orders,
  sum(amount) / sum(sum(amount)) OVER () AS share
FROM product_lines
GROUP BY stockcode
ORDER BY net_sales DESC
```

```sql product_concentration "How concentrated product sales are"
WITH r AS (
  SELECT *, row_number() OVER (ORDER BY net_sales DESC) AS rn,
         sum(share) OVER (ORDER BY net_sales DESC ROWS UNBOUNDED PRECEDING) AS cum_share
  FROM products
)
SELECT
  count(*) AS n_products,
  sum(share) FILTER (WHERE rn <= 10) AS top10_share,
  sum(share) FILTER (WHERE rn <= 100) AS top100_share,
  count(*) FILTER (WHERE cum_share - share < 0.5) AS products_for_half,
  max(description) FILTER (WHERE rn = 1) AS top_product,
  max(net_sales) FILTER (WHERE rn = 1) AS top_product_sales
FROM r
```

```kpi
- { label: "Products sold", value: product_concentration.n_products, format: int }
- { label: "Top 10 products' share", value: product_concentration.top10_share, format: pct }
- { label: "Top 100 products' share", value: product_concentration.top100_share, format: pct }
```

Product sales are spread wide: the top 10 of {{product_concentration.n_products | int}} products make up just **{{product_concentration.top10_share | pct}}** of net sales, and it takes **{{product_concentration.products_for_half | int}}** products to reach half. The biggest seller is **{{product_concentration.top_product | text}}** ({{product_concentration.top_product_sales | gbp_short}}). Products are ranked on net sales, so orders that were placed and then cancelled (such as the {{bulk.q1 | int}}-unit "{{bulk.d1 | text}}" order) do not inflate the list.

```table
{ data: products, columns: [stockcode, description, net_sales, net_units, orders, share], limit: 15, format: { net_sales: gbp, net_units: int, orders: int, share: pct } }
```

## 3. How many customers come back?

```sql cust_months "Months in which each known customer bought"
SELECT DISTINCT customer_id, month
FROM product_lines
WHERE kind = 'sale' AND customer_id IS NOT NULL
```

```sql cust_activity "Customer activity by months since first purchase"
WITH c AS (
  SELECT customer_id, month, min(month) OVER (PARTITION BY customer_id) AS cohort FROM cust_months
)
SELECT customer_id, cohort, datediff('month', cohort, month) AS k,
       datediff('month', cohort, DATE '2011-11-01') AS max_k   -- Nov 2011 = last full month
FROM c
```

```sql retention "Retention by first-purchase month"
SELECT
  strftime(cohort, '%Y-%m') AS first_month,
  count(*) FILTER (WHERE k = 0) AS new_customers,
  CASE WHEN max(max_k) >= 1  THEN count(*) FILTER (WHERE k = 1)  / new_customers END AS m1,
  CASE WHEN max(max_k) >= 2  THEN count(*) FILTER (WHERE k = 2)  / new_customers END AS m2,
  CASE WHEN max(max_k) >= 3  THEN count(*) FILTER (WHERE k = 3)  / new_customers END AS m3,
  CASE WHEN max(max_k) >= 6  THEN count(*) FILTER (WHERE k = 6)  / new_customers END AS m6,
  CASE WHEN max(max_k) >= 12 THEN count(*) FILTER (WHERE k = 12) / new_customers END AS m12,
  CASE WHEN max(max_k) >= 12 THEN count(DISTINCT customer_id) FILTER (WHERE k BETWEEN 1 AND 12) / new_customers END AS any_within_12m
FROM cust_activity
WHERE cohort <= DATE '2011-11-01'
GROUP BY cohort
ORDER BY cohort
```

```sql retention_curve "Average retention curve"
WITH ks AS (SELECT range AS k FROM range(1, 13)),
a AS (SELECT * FROM cust_activity WHERE cohort >= DATE '2010-01-01'),  -- Dec 2009 cohort mixes in older customers
cust AS (SELECT DISTINCT customer_id, max_k FROM a WHERE max_k >= 1)
SELECT
  ks.k AS months_after_first,
  (SELECT count(*) FROM a WHERE a.k = ks.k)
    / (SELECT count(*) FROM cust WHERE cust.max_k >= ks.k) AS retained
FROM ks
ORDER BY ks.k
```

```sql repeat "Repeat purchase headline"
WITH per_cust AS (
  SELECT customer_id, count(DISTINCT invoice) AS orders, min(month) AS cohort
  FROM product_lines WHERE kind = 'sale' AND customer_id IS NOT NULL
  GROUP BY customer_id
),
back12 AS (
  SELECT DISTINCT customer_id FROM cust_activity
  WHERE cohort BETWEEN DATE '2010-01-01' AND DATE '2010-11-01' AND k BETWEEN 1 AND 12
)
SELECT
  count(*) AS customers,
  count(*) FILTER (WHERE orders >= 2) / count(*) AS repeat_share,
  (SELECT count(*) FROM back12)
    / count(*) FILTER (WHERE cohort BETWEEN DATE '2010-01-01' AND DATE '2010-11-01') AS back_within_12m,
  (SELECT retained FROM retention_curve WHERE months_after_first = 1) AS avg_m1
FROM per_cust
```

```kpi
- { label: "Customers who ordered 2+ times", value: repeat.repeat_share, format: pct }
- { label: "New customers (Jan–Nov 2010) back within 12 months", value: repeat.back_within_12m, format: pct }
- { label: "Buy again the very next month", value: repeat.avg_m1, format: pct }
```

Of {{repeat.customers | int}} identified customers, **{{repeat.repeat_share | pct}}** ordered more than once over the two years. For customers whose first order was in Jan–Nov 2010 (so we can see a full year after), **{{repeat.back_within_12m | pct}}** bought again within 12 months — but only about **{{repeat.avg_m1 | pct}}** come back in the very next month, and the share buying in any later month drifts slowly down from there, with a small bump around the first anniversary (the next holiday season). The December 2009 group looks far more loyal because it includes long-standing customers whose earlier purchases are not in this data.

```chart
{ type: line, data: retention_curve, x: months_after_first, y: retained, variant: dots, format: pct, title: "Share of customers buying again N months after their first order", description: "New customers from Jan 2010 onwards, pooled; each point uses only customers observed for at least N months." }
```

```table
{ data: retention, columns: [first_month, new_customers, m1, m2, m3, m6, m12, any_within_12m], format: { new_customers: int, m1: pct, m2: pct, m3: pct, m6: pct, m12: pct, any_within_12m: pct } }
```

## 4. Which customers matter most?

```sql rfm_base "Recency, frequency and spend per customer"
SELECT
  customer_id,
  datediff('day', max(invoicedate) FILTER (WHERE kind = 'sale')::DATE, DATE '2011-12-10') AS recency_days,
  count(DISTINCT invoice) FILTER (WHERE kind = 'sale') AS orders,
  sum(amount) AS net_spend
FROM product_lines
WHERE customer_id IS NOT NULL
GROUP BY customer_id
HAVING count(*) FILTER (WHERE kind = 'sale') > 0
```

```sql rfm "RFM scores and segments"
WITH s AS (
  SELECT *,
    1 + least(4, floor(5 * percent_rank() OVER (ORDER BY recency_days DESC)))::INT AS r,
    1 + least(4, floor(5 * percent_rank() OVER (ORDER BY orders)))::INT AS f,
    1 + least(4, floor(5 * percent_rank() OVER (ORDER BY net_spend)))::INT AS m
  FROM rfm_base
)
SELECT *,
  CASE
    WHEN net_spend <= 0 THEN 'Fully refunded'
    WHEN r = 5 AND f >= 4 THEN 'Champions'
    WHEN r >= 3 AND f >= 4 THEN 'Loyal'
    WHEN r >= 4 AND f BETWEEN 2 AND 3 THEN 'Potential loyalists'
    WHEN r = 5 AND f = 1 THEN 'New customers'
    WHEN r = 4 AND f = 1 THEN 'Promising'
    WHEN r = 3 AND f = 3 THEN 'Need attention'
    WHEN r = 3 AND f <= 2 THEN 'About to sleep'
    WHEN r <= 2 AND f = 5 THEN 'Can''t lose them'
    WHEN r <= 2 AND f BETWEEN 3 AND 4 THEN 'At risk'
    ELSE 'Hibernating'
  END AS segment
FROM s
```

```sql rfm_segments "Segment summary"
SELECT
  segment,
  count(*) AS customers,
  count(*) / sum(count(*)) OVER () AS share_customers,
  sum(net_spend) AS net_spend,
  sum(net_spend) / sum(sum(net_spend)) OVER () AS share_spend,
  median(recency_days) AS median_days_since_last,
  avg(orders) AS avg_orders,
  avg(net_spend) AS avg_spend,
  CASE segment
    WHEN 'Champions' THEN 'Bought recently and often — reward, ask for referrals'
    WHEN 'Loyal' THEN 'Frequent buyers — upsell, loyalty perks'
    WHEN 'Potential loyalists' THEN 'Recent, a few orders — nudge to a habit'
    WHEN 'New customers' THEN 'First order very recently — onboard well'
    WHEN 'Promising' THEN 'Recent single order — follow up'
    WHEN 'Need attention' THEN 'Average on all counts — targeted offer'
    WHEN 'About to sleep' THEN 'Fading, few orders — reactivate cheaply'
    WHEN 'Can''t lose them' THEN 'Used to buy a lot, gone quiet — win back now'
    WHEN 'At risk' THEN 'Good past buyers drifting away — win-back campaign'
    WHEN 'Hibernating' THEN 'Long gone, few orders — low priority'
    ELSE 'Every purchase cancelled'
  END AS what_to_do
FROM rfm
GROUP BY segment
ORDER BY net_spend DESC
```

```sql rfm_headline "Champions and top-customer concentration"
WITH ranked AS (
  SELECT net_spend, row_number() OVER (ORDER BY net_spend DESC) AS rn, count(*) OVER () AS n FROM rfm
)
SELECT
  (SELECT share_customers FROM rfm_segments WHERE segment = 'Champions') AS champ_customers,
  (SELECT share_spend FROM rfm_segments WHERE segment = 'Champions') AS champ_spend,
  (SELECT customers FROM rfm_segments WHERE segment = 'Champions') AS champ_n,
  (SELECT share_customers + 0 FROM rfm_segments WHERE segment = 'At risk')
    + (SELECT share_customers FROM rfm_segments WHERE segment = 'Can''t lose them') AS atrisk_customers,
  (SELECT share_spend FROM rfm_segments WHERE segment = 'At risk')
    + (SELECT share_spend FROM rfm_segments WHERE segment = 'Can''t lose them') AS atrisk_spend,
  sum(net_spend) FILTER (WHERE rn <= n * 0.2) / sum(net_spend) AS top20_spend_share
FROM ranked
```

```kpi
- { label: "Champions — share of customers", value: rfm_headline.champ_customers, format: pct }
- { label: "Champions — share of spend", value: rfm_headline.champ_spend, format: pct }
- { label: "Top fifth of customers — share of spend", value: rfm_headline.top20_spend_share, format: pct }
```

**{{rfm_headline.champ_n | int}} Champions** — {{rfm_headline.champ_customers | pct}} of customers who bought recently and often — account for **{{rfm_headline.champ_spend | pct}}** of all customer spend, and the top fifth of customers by spend bring in {{rfm_headline.top20_spend_share | pct}}. The main risk is the *At risk* and *Can't lose them* groups: {{rfm_headline.atrisk_customers | pct}} of customers and {{rfm_headline.atrisk_spend | pct}} of spend from people who used to buy regularly but have gone quiet.

```chart
{ type: bar, data: rfm_segments, x: segment, y: [share_customers, share_spend], variant: horizontal, format: pct, title: "Share of customers vs share of spend, by segment" }
```

```table
{ data: rfm_segments, columns: [segment, customers, share_customers, net_spend, share_spend, median_days_since_last, avg_orders, avg_spend, what_to_do], format: { customers: int, share_customers: pct, net_spend: gbp, share_spend: pct, median_days_since_last: int, avg_orders: num, avg_spend: gbp } }
```

### Win-back list for marketing

```sql winback "At risk and Can't lose them customers, biggest past spenders first"
SELECT customer_id, segment, orders, net_spend, recency_days
FROM rfm
WHERE segment IN ('At risk', 'Can''t lose them')
ORDER BY net_spend DESC, customer_id
```

```sql winback_summary "Win-back list size"
SELECT count(*) AS customers, sum(net_spend) AS past_spend, median(recency_days) AS median_days FROM winback
```

The win-back list has **{{winback_summary.customers | int}} customers** who spent {{winback_summary.past_spend | gbp_short}} with us and last ordered a median of {{winback_summary.median_days | int}} days ago. The full list is the `winback` block (see Notes to download it).

```table
{ data: winback, columns: [customer_id, segment, orders, net_spend, recency_days], limit: 10, format: { customer_id: text, orders: int, net_spend: gbp, recency_days: int } }
```

## 5. What do cancellations and returns cost?

```sql credits "Cancellations, refunds and write-offs by type"
SELECT
  CASE
    WHEN kind = 'bad_debt' THEN 'Bad debt written off'
    WHEN line_type = 'product' THEN 'Cancelled or returned products'
    WHEN line_type = 'postage' THEN 'Postage refunded'
    WHEN line_type = 'fees' THEN 'Amazon, bank and charity fees'
    ELSE 'Manual credits, discounts and samples'
  END AS category,
  -sum(amount) AS cost,
  count(DISTINCT invoice) AS credit_notes
FROM items
WHERE kind IN ('cancellation', 'bad_debt') AND line_type <> 'test'
GROUP BY 1
ORDER BY cost DESC
```

```sql cancel_summary "Cancellation headline"
WITH p AS (
  SELECT
    sum(amount) FILTER (WHERE kind = 'sale') AS gross_sales,
    -sum(amount) FILTER (WHERE kind = 'cancellation') AS product_cancel,
    count(DISTINCT invoice) FILTER (WHERE kind = 'sale') AS orders,
    count(DISTINCT invoice) FILTER (WHERE kind = 'cancellation') AS cancel_notes,
    -sum(amount) FILTER (WHERE kind = 'cancellation' AND abs(quantity) < 50000) AS product_cancel_ex_bulk,
    count(DISTINCT customer_id) FILTER (WHERE kind = 'cancellation') AS cancel_customers,
    count(DISTINCT customer_id) FILTER (WHERE kind = 'sale') AS customers
  FROM product_lines
)
SELECT *,
  product_cancel / gross_sales AS cancel_rate,
  product_cancel_ex_bulk / gross_sales AS cancel_rate_ex_bulk,
  product_cancel - product_cancel_ex_bulk AS bulk_cancel,
  cancel_notes / orders AS notes_per_order,
  cancel_customers / customers AS customers_cancelling,
  (SELECT sum(cost) FROM credits) AS total_credits,
  (SELECT sum(cost) FROM credits WHERE category <> 'Cancelled or returned products') AS other_credits
FROM p
```

```sql bulk "The two bulk orders that were reversed"
WITH b AS (
  SELECT -quantity AS q, description AS d, row_number() OVER (ORDER BY quantity) AS rn
  FROM product_lines WHERE kind = 'cancellation' AND abs(quantity) >= 50000
)
SELECT max(q) FILTER (WHERE rn = 1) AS q1, max(d) FILTER (WHERE rn = 1) AS d1,
       max(q) FILTER (WHERE rn = 2) AS q2, max(d) FILTER (WHERE rn = 2) AS d2
FROM b
```

```kpi
- { label: "Products cancelled or returned", value: cancel_summary.product_cancel, format: gbp_short }
- { label: "As share of gross product sales", value: cancel_summary.cancel_rate, format: pct }
- { label: "All credits and write-offs", value: cancel_summary.total_credits, format: gbp_short }
```

Over the two years, **{{cancel_summary.product_cancel | gbp_short}}** of product sales were cancelled or returned — **{{cancel_summary.cancel_rate | pct}}** of gross product sales. {{cancel_summary.bulk_cancel | gbp_short}} of that is just two giant orders ({{bulk.q1 | int}} × {{bulk.d1 | text}} and {{bulk.q2 | int}} × {{bulk.d2 | text}}) that were reversed soon after being placed; without them the rate is {{cancel_summary.cancel_rate_ex_bulk | pct}}. Credit notes for products were raised at a rate equal to {{cancel_summary.notes_per_order | pct}} of the number of orders, and {{cancel_summary.customers_cancelling | pct}} of customers cancelled something at least once. On top of product returns, another **{{cancel_summary.other_credits | gbp_short}}** went out as fees, manual credits, refunded postage and bad debt, bringing all credits and write-offs to {{cancel_summary.total_credits | gbp_short}}.

```chart
{ type: bar, data: credits, x: category, y: cost, variant: horizontal, format: gbp_short, title: "What credits and write-offs cost (£)" }
```

```sql monthly_cancel "Monthly cancellation rate"
SELECT month, cancelled, gross_sales, cancelled / gross_sales AS cancel_rate FROM monthly
```

```chart
{ type: line, data: monthly_cancel, x: month, y: cancel_rate, variant: dots, format: pct, title: "Cancelled and returned products as a share of gross sales, by month", description: "Spikes in Jan 2011 and Dec 2011 are the two bulk orders that were reversed." }
```

```sql top_cancelled "Most cancelled products"
SELECT
  stockcode,
  mode(description) AS description,
  -sum(amount) AS cancelled_value,
  -sum(quantity) AS cancelled_units,
  count(DISTINCT invoice) AS credit_notes
FROM product_lines
WHERE kind = 'cancellation'
GROUP BY stockcode
ORDER BY cancelled_value DESC
LIMIT 15
```

```table
{ data: top_cancelled, columns: [stockcode, description, cancelled_value, cancelled_units, credit_notes], format: { cancelled_value: gbp, cancelled_units: int, credit_notes: int } }
```

## Notes

- **Source**: `data/online_retail_II.xlsx`, sheets "Year 2009-2010" and "Year 2010-2011", 1 Dec 2009 – 9 Dec 2011. Both sheets contain 1–9 Dec 2010 with identical rows; that period is counted once.
- **Net sales** = product sales minus cancelled/returned products. Postage, carriage, Amazon/bank fees, manual adjustments, discounts, samples, bad-debt entries and test items are excluded from sales. Lines with zero price or negative quantity on a normal invoice (stock write-offs, {{stock_adj.lines | int}} lines) carry no value and are ignored.
```sql stock_adj "Zero-value stock adjustment lines"
SELECT count(*) AS lines FROM items WHERE kind = 'stock_adjustment'
```

- **Orders** = distinct invoice numbers with at least one product sale. Cancellations are invoices starting with "C"; bad-debt adjustments start with "A".
- **Customers**: about a fifth of sales lines have no customer ID (guest checkout); they count in sales and country figures but not in retention or segments.
- **Retention**: a customer's cohort is the month of their first order seen in this data. "Mth N" = share of the cohort who bought in the Nth month after it. Nov 2011 is the last full month; later months show blank. The Dec 2009 cohort includes customers who bought before the data starts.
- **Segments** (RFM): each customer gets a 1–5 score for recency (days since last order, as of 10 Dec 2011), frequency (number of orders) and spend (net), by rank among all customers. Segments use the recency and frequency scores with the standard RFM segment map; customers whose purchases were all cancelled are listed separately.
- **Win-back CSV**: `databook export --block winback winback.csv` writes every customer on the list (the table above shows the top 10).
- The 12-month comparison uses Dec 2009–Nov 2010 vs Dec 2010–Nov 2011 so both periods are full and include one holiday season.
