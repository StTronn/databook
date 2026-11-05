# GA4 pack (BigQuery export)

Raw GA4 events exist only in the BigQuery export (GA4 Admin → BigQuery links; daily tables `events_YYYYMMDD`). The GA4
UI/Data API gives pre-aggregated, sampled, thresholded reports — not journeys. Get data (user's own gcloud login):
`bq query --use_legacy_sql=false --format=json --max_rows=1000000 'SELECT * FROM \`proj.analytics_123.events_*\`
WHERE _TABLE_SUFFIX BETWEEN "20240101" AND "20240131"' > data/ga4_events_202401.json` (or `bq extract
--destination_format=NEWLINE_DELIMITED_JSON` → .jsonl, or PARQUET → loads as-is with native nested types).

Table `ga4_events`, one row per event: event_date DATE (property time zone), event_timestamp TIMESTAMPTZ (UTC,
microsecond-exact), event_name, user_pseudo_id (device/browser id, TEXT), user_id (your login id, often NULL),
nested event_params / device / geo / traffic_source / collected_traffic_source / ecommerce / items as JSON text.

Params (int_value arrives as a string; from_json casts it):
```sql
WITH e AS (SELECT *, from_json(event_params, '[{"key":"VARCHAR","value":{"string_value":"VARCHAR","int_value":"BIGINT",
             "double_value":"DOUBLE"}}]') AS p FROM ga4_events)
SELECT *, list_filter(p, lambda x: x.key = 'ga_session_id')[1].value.int_value AS ga_session_id,
          list_filter(p, lambda x: x.key = 'page_location')[1].value.string_value AS page_location
FROM e
```
Session = (user_pseudo_id, ga_session_id) — ga_session_id alone is NOT unique. `traffic_source` is the user's FIRST
acquisition, not the session's; per-session source/medium = `session_traffic_source_last_click` (exports since mid-2024)
else `collected_traffic_source` on the session's first event. Revenue: ecommerce->>'purchase_revenue' on purchase
events; dedupe by ecommerce->>'transaction_id' (GA4 can log a purchase twice). Funnels: count distinct sessions reaching
each step in order within the session (min event_timestamp per step, step n timestamp ≥ step n−1).
