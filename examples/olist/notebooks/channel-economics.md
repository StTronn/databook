---
title: Channel economics
---
# Channel economics

Which marketing channels bring us sellers who actually sell, and what each channel costs us. All money is in Brazilian reais (R$).

## Inputs (assumptions — edit here)

These are **planning assumptions, not data**. Change a number here and every cost and commission figure below updates.

```sql in_cpl "Assumed cost per lead by channel (R$)"
SELECT * FROM (VALUES
  ('paid_search',       60),
  ('social',            40),
  ('display',           50),
  ('email',             10),
  ('organic_search',    15),
  ('referral',          30),
  ('direct_traffic',     5),
  ('other_publicities', 40),
  ('other',             20),
  ('unknown',           20)
) AS t(channel, cost_per_lead)
```

```sql in_params "Other assumptions"
SELECT 0.10 AS commission_rate,          -- our commission, share of seller revenue
       0.60 AS target_activation,        -- scenario: active sellers as a share of won sellers
       DATE '2018-08-31' AS sales_end,   -- last day of sales data
       100 AS min_leads,                 -- channels need this many leads to be ranked in section 1
       10 AS min_active                  -- channels need this many active sellers to be ranked in section 3
```

```table
{ data: in_cpl, columns: [channel, cost_per_lead], format: { cost_per_lead: num } }
```

```table
{ data: in_params, columns: [commission_rate, target_activation, sales_end, min_leads, min_active], format: { commission_rate: pct, target_activation: pct, sales_end: date, min_leads: int, min_active: int } }
```

```sql seller_rev "Revenue per seller from delivered orders"
SELECT oi.seller_id,
       sum(oi.price) AS revenue,
       count(DISTINCT oi.order_id) AS orders
FROM order_items oi
JOIN orders o ON o.order_id = oi.order_id
WHERE o.order_status = 'delivered'
GROUP BY oi.seller_id
```

```sql leads "One row per marketing-qualified lead, with outcome"
SELECT q.mql_id,
       coalesce(q.origin, 'unknown') AS channel,
       c.seller_id,
       c.won_date,
       coalesce(c.business_segment, '(no segment)') AS segment,
       c.seller_id IS NOT NULL AS won,
       r.seller_id IS NOT NULL AS active,
       coalesce(r.revenue, 0) AS revenue,
       -- months on the books from win to end of sales data; at least 1 so a seller won days before the cut-off isn't inflated
       CASE WHEN c.seller_id IS NOT NULL
            THEN greatest(date_diff('day', c.won_date::DATE, (SELECT sales_end FROM in_params)) / 30.4375, 1)
       END AS months_since_won
FROM leads_qualified q
LEFT JOIN leads_closed c ON c.mql_id = q.mql_id
LEFT JOIN seller_rev r ON r.seller_id = c.seller_id
```

```sql kpis
SELECT count(*) AS leads,
       count(*) FILTER (WHERE won) AS won,
       count(*) FILTER (WHERE won) / count(*) AS win_rate,
       count(*) FILTER (WHERE active) AS active,
       count(*) FILTER (WHERE active) / count(*) FILTER (WHERE won) AS active_share,
       sum(revenue) AS revenue,
       count(*) FILTER (WHERE won_date > (SELECT sales_end FROM in_params)) AS won_after_end
FROM leads
```

```kpi
- { label: Qualified leads, value: kpis.leads, format: int }
- { label: Won sellers, value: kpis.won, format: int }
- { label: Win rate (won ÷ leads), value: kpis.win_rate, format: pct }
- { label: Active sellers, value: kpis.active, format: int }
- { label: Active share of won, value: kpis.active_share, format: pct }
- { label: Revenue from these sellers (R$), value: kpis.revenue, format: num }
```

Of **{{kpis.leads | int}}** qualified leads we signed **{{kpis.won | int}}** sellers ({{kpis.win_rate | pct}}), but only **{{kpis.active | int}}** of them ({{kpis.active_share | pct}} of won) have sold anything that was delivered. Together they sold **R$ {{kpis.revenue | num}}**.

## 1. Which channels convert?

```sql by_channel "Leads → won → active, by channel"
SELECT channel,
       count(*) AS leads,
       count(*) FILTER (WHERE won) AS won,
       count(*) FILTER (WHERE active) AS active,
       count(*) FILTER (WHERE won) / count(*) AS win_rate,
       CASE WHEN count(*) FILTER (WHERE won) > 0
            THEN count(*) FILTER (WHERE active) / count(*) FILTER (WHERE won) END AS active_of_won,
       count(*) FILTER (WHERE active) / count(*) AS active_of_leads,
       sum(revenue) AS revenue
FROM leads
GROUP BY channel
```

```sql conv_best
SELECT arg_max(channel, active_of_leads) AS best_channel,
       max(active_of_leads) AS best_rate,
       arg_max(channel, active) AS most_active_channel,
       max(active) AS most_active
FROM by_channel WHERE leads >= (SELECT min_leads FROM in_params)
```

**{{conv_best.best_channel | text}}** turns the largest share of its leads into active sellers ({{conv_best.best_rate | pct}}, among channels with at least {{in_params.min_leads | int}} leads); **{{conv_best.most_active_channel | text}}** brings the most active sellers in absolute terms ({{conv_best.most_active | int}}).

```chart
{ type: bar, data: by_channel, x: channel, y: [won, active], variant: horizontal, title: "Won and active sellers by channel" }
```

```table
{ data: by_channel, columns: [channel, leads, won, active, win_rate, active_of_won, active_of_leads], sort: active desc, format: { leads: int, won: int, active: int, win_rate: pct, active_of_won: pct, active_of_leads: pct } }
```

## 2. What do these sellers sell?

```sql by_segment "Revenue by business segment (won sellers)"
SELECT segment,
       count(*) FILTER (WHERE won) AS won,
       count(*) FILTER (WHERE active) AS active,
       sum(revenue) AS revenue,
       sum(revenue) / (SELECT sum(revenue) FROM leads) AS share
FROM leads
WHERE won
GROUP BY segment
HAVING sum(revenue) > 0
```

```sql top_seller "Concentration: the single biggest seller"
SELECT arg_max(segment, revenue) AS top_segment,
       arg_max(channel, revenue) AS top_channel,
       max(revenue) AS top_revenue,
       max(revenue) / sum(revenue) AS top_share,
       (SELECT arg_max(segment, revenue) FROM by_segment) AS lead_segment,
       (SELECT max(share) FROM by_segment) AS lead_segment_share
FROM leads WHERE won
```

```kpi
- { label: Top seller's revenue (R$), value: top_seller.top_revenue, format: num }
- { label: Top seller's share of all revenue, value: top_seller.top_share, format: pct }
- { label: Largest segment's share, value: top_seller.lead_segment_share, format: pct }
```

**{{top_seller.lead_segment | text}}** is the biggest segment with {{top_seller.lead_segment_share | pct}} of revenue. One seller alone — in {{top_seller.top_segment | text}}, from {{top_seller.top_channel | text}} — accounts for **{{top_seller.top_share | pct}}** of all revenue from marketing-acquired sellers, so channel and segment totals below lean heavily on it.

```chart
{ type: bar, data: by_segment, x: segment, y: revenue, variant: horizontal, format: num, title: "Revenue by business segment (R$)" }
```

```table
{ data: by_segment, columns: [segment, won, active, revenue, share], sort: revenue desc, format: { won: int, active: int, revenue: num, share: pct } }
```

## 3. Which channel's sellers earn most?

Revenue per seller-month = a seller's revenue ÷ months from their win date to {{in_params.sales_end | date}}, so sellers won late aren't penalised. Only active sellers are included.

```sql per_month "Revenue per seller-month, active sellers, by channel"
SELECT channel,
       count(*) AS active_sellers,
       median(revenue / months_since_won) AS median_rev_per_month,
       avg(revenue / months_since_won) AS mean_rev_per_month,
       median(revenue) AS median_revenue
FROM leads
WHERE active
GROUP BY channel
```

```sql per_month_best
SELECT arg_max(channel, median_rev_per_month) AS best_channel,
       max(median_rev_per_month) AS best_median,
       arg_max(channel, mean_rev_per_month) AS best_mean_channel,
       max(mean_rev_per_month) AS best_mean
FROM per_month WHERE active_sellers >= (SELECT min_active FROM in_params)
```

Among channels with at least {{in_params.min_active | int}} active sellers, a typical **{{per_month_best.best_channel | text}}** seller earns the most: a median **R$ {{per_month_best.best_median | num}}** per month. Means sit well above medians because a few large sellers pull them up; the highest mean is {{per_month_best.best_mean_channel | text}} (R$ {{per_month_best.best_mean | num}} per month). Channels with only a handful of active sellers are noisy.

```chart
{ type: bar, data: per_month, x: channel, y: [median_rev_per_month, mean_rev_per_month], format: num, title: "Revenue per seller-month (R$), active sellers" }
```

```table
{ data: per_month, columns: [channel, active_sellers, median_rev_per_month, mean_rev_per_month], sort: median_rev_per_month desc, format: { active_sellers: int, median_rev_per_month: num, mean_rev_per_month: num } }
```

## 4. What does each channel cost us?

Costs use the assumed cost per lead and commission rate from **Inputs** above — they are assumptions, not data.

```sql econ "Channel cost and commission (assumptions applied)"
SELECT b.channel, b.leads, b.won, b.active, b.revenue,
       i.cost_per_lead,
       b.leads * i.cost_per_lead AS cost,
       CASE WHEN b.won > 0 THEN b.leads * i.cost_per_lead / b.won END AS cost_per_won,
       CASE WHEN b.active > 0 THEN b.leads * i.cost_per_lead / b.active END AS cost_per_active,
       b.revenue * p.commission_rate AS commission,
       b.revenue * p.commission_rate / (b.leads * i.cost_per_lead) AS commission_to_cost
FROM by_channel b
JOIN in_cpl i ON i.channel = b.channel
CROSS JOIN in_params p
```

```sql econ_total
SELECT sum(cost) AS cost,
       sum(cost) / sum(won) AS cost_per_won,
       sum(cost) / sum(active) AS cost_per_active,
       sum(commission) AS commission,
       sum(commission) / sum(cost) AS commission_to_cost,
       arg_max(channel, commission_to_cost) AS best_channel,
       max(commission_to_cost) AS best_ratio,
       arg_min(channel, commission_to_cost) AS worst_channel,
       min(commission_to_cost) AS worst_ratio,
       count(*) FILTER (WHERE commission_to_cost >= 1) AS channels_paying_back
FROM econ
```

```kpi
- { label: Total acquisition cost (R$), value: econ_total.cost, format: num }
- { label: Cost per won seller (R$), value: econ_total.cost_per_won, format: num }
- { label: Cost per active seller (R$), value: econ_total.cost_per_active, format: num }
- { label: Commission earned (R$), value: econ_total.commission, format: num }
- { label: Commission ÷ cost, value: econ_total.commission_to_cost, format: pct }
```

Under these assumptions, commission so far covers **{{econ_total.commission_to_cost | pct}}** of what we spent acquiring the leads. **{{econ_total.best_channel | text}}** pays back best ({{econ_total.best_ratio | pct}} of its cost) and **{{econ_total.worst_channel | text}}** worst ({{econ_total.worst_ratio | pct}}); {{econ_total.channels_paying_back | int}} channel(s) have earned back their cost.

```chart
{ type: bar, data: econ, x: channel, y: [cost, commission], format: num, title: "Assumed cost vs commission earned (R$)" }
```

```table
{ data: econ, columns: [channel, leads, cost_per_lead, cost, cost_per_won, cost_per_active, commission, commission_to_cost], sort: commission_to_cost desc, format: { leads: int, cost_per_lead: num, cost: num, cost_per_won: num, cost_per_active: num, commission: num, commission_to_cost: pct } }
```

## 5. What if activation rose to the target?

Every channel's active sellers rise to the target share of its won sellers (channels already above it stay as they are). Each new active seller earns the channel's median revenue per active seller.

```sql scenario "Activation scenario by channel"
WITH med AS (
  SELECT channel, median(revenue) AS median_revenue FROM leads WHERE active GROUP BY channel
), s AS (
  SELECT e.channel, e.won, e.active, e.cost, e.commission,
         coalesce(m.median_revenue, 0) AS median_revenue,
         greatest(round(e.won * p.target_activation) - e.active, 0) AS new_active,
         p.commission_rate
  FROM econ e
  LEFT JOIN med m ON m.channel = e.channel
  CROSS JOIN in_params p
)
SELECT channel, won, active, commission,
       new_active,
       active + new_active AS scenario_active,
       median_revenue,
       new_active * median_revenue AS added_revenue,
       new_active * median_revenue * commission_rate AS added_commission,
       commission + new_active * median_revenue * commission_rate AS scenario_commission,
       cost,
       commission / cost AS commission_to_cost,
       (commission + new_active * median_revenue * commission_rate) / cost AS scenario_commission_to_cost
FROM s
```

```sql scenario_total
SELECT sum(new_active) AS new_active,
       sum(active) AS active,
       sum(scenario_active) AS scenario_active,
       sum(added_revenue) AS added_revenue,
       sum(added_commission) AS added_commission,
       sum(commission) / sum(cost) AS commission_to_cost,
       sum(scenario_commission) / sum(cost) AS scenario_commission_to_cost,
       sum(cost) / sum(scenario_active) AS scenario_cost_per_active
FROM scenario
```

```kpi
- { label: Active sellers, value: scenario_total.scenario_active, format: int, compare: scenario_total.active }
- { label: Added revenue (R$), value: scenario_total.added_revenue, format: num }
- { label: Added commission (R$), value: scenario_total.added_commission, format: num }
- { label: Commission ÷ cost, value: scenario_total.scenario_commission_to_cost, format: pct, compare: scenario_total.commission_to_cost }
```

Reaching {{in_params.target_activation | pct}} activation would add **{{scenario_total.new_active | int}}** active sellers and about **R$ {{scenario_total.added_revenue | num}}** of revenue, lifting commission from {{scenario_total.commission_to_cost | pct}} to **{{scenario_total.scenario_commission_to_cost | pct}}** of acquisition cost, and cutting cost per active seller to R$ {{scenario_total.scenario_cost_per_active | num}}. Because new sellers are valued at the median (not the mean), this is a conservative estimate.

```chart
{ type: bar, data: scenario, x: channel, y: [commission_to_cost, scenario_commission_to_cost], format: pct, title: "Commission ÷ cost: today vs target activation" }
```

```table
{ data: scenario, columns: [channel, won, active, new_active, median_revenue, added_revenue, added_commission, commission_to_cost, scenario_commission_to_cost], sort: added_revenue desc, format: { won: int, active: int, new_active: int, median_revenue: num, added_revenue: num, added_commission: num, commission_to_cost: pct, scenario_commission_to_cost: pct } }
```

## Notes

- **Assumptions, not data:** cost per lead, the commission rate and the activation target all come from the **Inputs** blocks at the top. Every cost, commission and scenario figure depends on them.
- **Channel** = `origin` in `leads_qualified`; empty origins are counted as *unknown*.
- **Won** = the lead appears in `leads_closed`. **Active** = a won seller with at least one item in a *delivered* order.
- **Revenue** = sum of item `price` on delivered orders, in R$, freight excluded (same definition as the monthly review).
- **Sales window:** sales data ends {{in_params.sales_end | date}}. {{kpis.won_after_end | int}} sellers were won after that date, so they could not have sold yet; they count as won (and in the activation scenario's base) but not as active. Seller-months run from the win date to the end of the window, with a minimum of 1 month.
- **Unknown** includes leads whose origin was recorded as *unknown* and those with no origin at all; it is the best-converting group, so tracking origins better would sharpen this analysis.
- **Scenario:** new active sellers are rounded to whole sellers. A channel with no active sellers today (other_publicities) has no median to borrow, so its new sellers add no revenue.
- Revenue is concentrated: one watches seller earns about a sixth of the total, which lifts the *unknown* channel and the watches segment.
- Lead dates run June 2017 – May 2018. Source: `data/olist.sqlite`.
