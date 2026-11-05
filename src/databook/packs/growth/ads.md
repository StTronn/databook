# Ads packs (Meta, Google Ads)

Meta — Ads Manager → pick level (campaign / ad set / ad) → Breakdown → By time → Day → Reports → Export table data (.csv
or .xlsx). Table `meta_ads`, one row per entity per day (if "Day" was chosen; else per reporting window): day,
reporting_starts/ends, campaign_name / ad_set_name / ad_name (+ *_id if added), impressions, reach, link_clicks, results
+ result_indicator (what "results" counts — differs per campaign; never sum results across indicators), amount_spent.
The export puts the account currency in headers ("Amount spent (USD)"): it is stripped and a `currency` column added.

Google Ads — Campaigns (or Ad groups / Keywords) → segment by Day → Download → CSV. Title and date-range lines are
skipped, "Total: …" rows dropped, "--" → NULL; UTF-16 "Excel CSV" also loads. Table `google_ads`: day, campaign,
campaign_id, cost (account currency; add the "Currency code" column to the report), impr, clicks, conversions,
conv_value (fractional: data-driven attribution). Percent columns (CTR, Conv. rate) stay text: recompute from counts.

Both: export by Day, one file per non-overlapping range (no row key; identical rows across files are flagged).
Platform conversions are each platform's own attributed claim — they overlap; never add Meta results to Google
conversions. Blended CAC = total spend / new customers from the source of truth (Shopify first orders / Stripe):
```sql
SELECT CAST(day AS DATE) AS d, 'meta' AS channel, amount_spent AS spend, currency FROM meta_ads
UNION ALL SELECT CAST(day AS DATE), 'google', cost, currency_code FROM google_ads
```
