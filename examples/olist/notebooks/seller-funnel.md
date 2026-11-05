---
title: Seller acquisition funnel
---
# Seller acquisition funnel

Olist brings in sellers through marketing: a lead fills in a form, a sales rep closes the deal, then the seller lists
products and (hopefully) sells. Which channels bring sellers who actually sell, and where do we lose the rest?

```sql settings "Funnel windows"
SELECT DATE '2018-01-01' AS leads_from,  -- closed-deal records start in Dec 2017, so earlier leads can't show a win
       90 AS won_within_days,          -- a deal counts as won if it closes within this many days of first contact
       60 AS sale_within_days,         -- a first sale counts if it happens within this many days of the win
       DATE '2018-08-31' AS sales_end, -- last day of complete sales data
       200 AS min_leads                -- channels need this many leads to be compared
```

```sql first_sale "First order date per seller"
SELECT oi.seller_id, min(o.order_purchase_timestamp)::DATE AS first_sale
FROM order_items oi
JOIN orders o ON o.order_id = oi.order_id
WHERE o.order_status NOT IN ('canceled', 'unavailable')
GROUP BY oi.seller_id
```

```sql journey "One row per lead: did it reach each step, in time?"
SELECT q.mql_id,
       coalesce(q.origin, 'unknown') AS channel,
       date_trunc('month', q.first_contact_date)::DATE AS lead_month,
       q.first_contact_date::DATE AS contacted,
       c.won_date::DATE AS won_on,
       f.first_sale,
       c.won_date IS NOT NULL
         AND c.won_date::DATE BETWEEN q.first_contact_date::DATE
                                  AND q.first_contact_date::DATE + s.won_within_days AS is_won,
       is_won AND f.first_sale BETWEEN c.won_date::DATE AND c.won_date::DATE + s.sale_within_days AS is_sold,
       -- a lead's outcome is final once both windows have passed before the data ends
       q.first_contact_date::DATE + s.won_within_days + s.sale_within_days <= s.sales_end AS complete
FROM leads_qualified q
CROSS JOIN settings s
LEFT JOIN leads_closed c ON c.mql_id = q.mql_id
LEFT JOIN first_sale f ON f.seller_id = c.seller_id
WHERE q.first_contact_date >= s.leads_from
```

```sql totals "Funnel totals, leads whose outcome is final"
SELECT count(*) AS leads,
       count(*) FILTER (WHERE is_won) AS won,
       count(*) FILTER (WHERE is_sold) AS sold,
       sold / leads AS lead_to_sale,
       won / leads AS lead_to_won,
       sold / won AS won_to_sale,
       1 - sold / won AS won_never_sold
FROM journey
WHERE complete
```

```sql range "Lead dates covered"
SELECT min(contacted) FILTER (WHERE complete) AS first_lead,
       max(contacted) FILTER (WHERE complete) AS last_lead,
       count(*) FILTER (WHERE NOT complete) AS pending
FROM journey
```

Of {{totals.leads | int}} leads, only {{totals.sold | int}} became sellers who made a sale: **{{totals.lead_to_sale | pct}}**.
The biggest leak is after the deal is won: **{{totals.won_never_sold | pct}}** of won sellers never sold within
{{settings.sale_within_days | int}} days.

```kpi
- { label: Leads, value: totals.leads, format: int }
- { label: Won, value: totals.won, format: int }
- { label: Made a first sale, value: totals.sold, format: int }
- { label: Lead → selling seller, value: totals.lead_to_sale, format: pct }
```

## 1. Where do we lose leads?

```sql stages "Funnel stages"
SELECT stage, n FROM (
  SELECT 1 AS k, 'Lead' AS stage, leads AS n FROM totals UNION ALL
  SELECT 2, 'Deal won', won FROM totals UNION ALL
  SELECT 3, 'First sale', sold FROM totals
) ORDER BY k
```

```chart
{ type: funnel, data: stages, x: stage, y: n, title: Leads by stage,
  description: Leads whose outcome is final }
```

{{totals.lead_to_won | pct}} of leads become a won deal, and {{totals.won_to_sale | pct}} of won deals make a first sale.

## 2. Which channels bring sellers who sell?

```sql by_channel "Funnel by channel"
SELECT channel,
       count(*) AS leads,
       count(*) FILTER (WHERE is_won) AS won,
       count(*) FILTER (WHERE is_sold) AS sold,
       won / leads AS lead_to_won,
       CASE WHEN won > 0 THEN sold / won END AS won_to_sale,
       sold / leads AS lead_to_sale
FROM journey
WHERE complete
GROUP BY channel
ORDER BY lead_to_sale DESC, leads DESC
```

```sql ranked "Known channels with enough leads to compare"
SELECT * FROM by_channel WHERE leads >= (SELECT min_leads FROM settings) AND channel <> 'unknown'
ORDER BY lead_to_sale DESC, channel
```

```sql best "Best channel"
SELECT channel, lead_to_sale FROM ranked ORDER BY lead_to_sale DESC, channel LIMIT 1
```

```sql worst "Worst channel"
SELECT channel, lead_to_sale FROM ranked ORDER BY lead_to_sale, channel LIMIT 1
```

Among known channels with at least {{settings.min_leads | int}} leads, **{{best.channel | text}}** turns {{best.lead_to_sale | pct}} of leads into
selling sellers; **{{worst.channel | text}}** only {{worst.lead_to_sale | pct}}.

```chart
{ type: hbar, data: ranked, x: channel, y: lead_to_sale, format: pct, title: Lead → selling seller by channel,
  description: Channels with enough leads to compare }
```

```table
{ data: by_channel, columns: [channel, leads, won, sold, lead_to_won, won_to_sale, lead_to_sale],
  format: { lead_to_won: pct, won_to_sale: pct, lead_to_sale: pct } }
```

## 3. How fast do leads move?

```sql speed "Median days between steps, by channel"
SELECT channel,
       count(*) AS sold,
       median(won_on - contacted) AS days_to_win,
       median(first_sale - won_on) AS days_to_first_sale
FROM journey
WHERE is_sold AND complete
GROUP BY channel
HAVING count(*) >= 10
ORDER BY days_to_win
```

```sql speed_all "Median days, all channels"
SELECT median(won_on - contacted) AS days_to_win, median(first_sale - won_on) AS days_to_first_sale
FROM journey WHERE is_sold AND complete
```

A seller who makes it typically closes {{speed_all.days_to_win | int}} days after first contact and sells
{{speed_all.days_to_first_sale | int}} days after that.

```chart
{ type: bar, data: speed, x: channel, y: [days_to_win, days_to_first_sale], title: Median days per step,
  description: Sellers who made a first sale; channels with at least 10 }
```

## 4. Which months are final?

```sql by_month "Conversion by the month the lead came in"
SELECT lead_month,
       count(*) AS leads,
       count(*) FILTER (WHERE is_sold) AS sold,
       sold / leads AS lead_to_sale,
       bool_and(complete) AS complete
FROM journey
GROUP BY lead_month
ORDER BY lead_month
```

Only months whose leads have had the full {{settings.won_within_days | int}} + {{settings.sale_within_days | int}} days
before the data ends are counted in the totals above; later months are still in progress.

```table
{ data: by_month, columns: [lead_month, leads, sold, lead_to_sale, complete],
  format: { lead_month: date, lead_to_sale: pct } }
```

## Notes

- Leads before {{settings.leads_from | date}} are left out: Olist's closed-deal records only start in December 2017,
  so earlier leads would look like they never converted.
- Data: Olist's marketing funnel (leads from {{range.first_lead | date}} to {{range.last_lead | date}}) joined to its
  real orders. Leads come from `leads_qualified`, won deals from `leads_closed`, first sales from `order_items`.
- A lead counts as won only if the deal closed within {{settings.won_within_days | int}} days of first contact, and as
  selling only if the seller's first non-cancelled order came within {{settings.sale_within_days | int}} days of the
  win. Change the windows in the first block.
- Leads contacted too recently for both windows to pass before {{settings.sales_end | date}} are left out of the
  totals ({{range.pending | int}} leads); the monthly table marks their months as not complete.
