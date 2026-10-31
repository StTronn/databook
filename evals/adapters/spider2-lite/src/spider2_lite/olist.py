"""Olist bundles: Spider2-lite questions on the Olist marketplace db plus our own questions, asked as one business request.

Our questions state their definitions in the request (vague wording made earlier Spider2 golds ungradable), so a wrong
answer means a wrong computation, not a different reading. Gold for our questions comes from the reference code below;
evals/tests/test_olist.py recomputes every one independently in pandas and also checks that Spider2's golds (computed on
the `Brazilian_E_Commerce` copy) hold on `E_commerce`, the db these tasks ship (same orders data + seller leads).
Grader constraints (compare.py): numbers match within 0.01 absolute → rates are percent; text matches exactly.
"""
from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass, field
from typing import Callable

import pandas as pd

DB = "E_commerce"
CUTOFF = "2018-08-31"                           # last day of sales data
CPL = {"paid_search": 60, "social": 40, "display": 50, "email": 10, "organic_search": 15, "referral": 30,
       "direct_traffic": 5, "other_publicities": 40, "other": 20, "unknown": 20}     # R$ per lead: stated assumptions
COMMISSION = 0.10


@dataclass(frozen=True)
class Question:
    id: str                                     # gold file stem / bundle id, e.g. olist_mr_q3
    text: str
    gold: Callable[[sqlite3.Connection], pd.DataFrame]
    standard: dict = field(default_factory=lambda: {"condition_cols": [], "ignore_order": True})


def _sql(con, q: str) -> pd.DataFrame:
    return pd.read_sql_query(q, con)


_DELIVERED = """d AS (SELECT o.order_id, o.order_purchase_timestamp AS ts, c.customer_unique_id AS u,
                            c.customer_city AS city, c.customer_state AS state
                     FROM orders o JOIN customers c USING (customer_id) WHERE o.order_status = 'delivered')"""


def mr_kpis(con) -> pd.DataFrame:
    return _sql(con, f"""WITH {_DELIVERED}
        SELECT substr(d.ts, 1, 7) AS month, sum(i.price) AS revenue, count(DISTINCT d.order_id) AS orders,
               count(DISTINCT d.u) AS customers, sum(i.price) / count(DISTINCT d.order_id) AS aov
        FROM d JOIN order_items i USING (order_id)
        WHERE substr(d.ts, 1, 7) IN ('2017-08', '2018-07', '2018-08') GROUP BY 1 ORDER BY 1""")


def mr_categories(con) -> pd.DataFrame:
    df = _sql(con, f"""WITH {_DELIVERED},
        r AS (SELECT coalesce(t.product_category_name_english, nullif(p.product_category_name, ''), 'unknown') AS category,
                     sum(i.price) AS revenue
              FROM d JOIN order_items i USING (order_id) JOIN products p USING (product_id)
              LEFT JOIN product_category_name_translation t ON t.product_category_name = p.product_category_name
              WHERE d.ts >= '2017-09-01' AND d.ts < '2018-09-01' GROUP BY 1)
        SELECT category, revenue, revenue * 100.0 / (SELECT sum(revenue) FROM r) AS share_pct
        FROM r ORDER BY revenue DESC LIMIT 11""")
    assert df.revenue.iloc[9] - df.revenue.iloc[10] > 0.01, "tie at rank 10: the top 10 would be ambiguous"
    return df.head(10)


def mr_top_customers(con) -> pd.DataFrame:
    df = _sql(con, f"""WITH {_DELIVERED},
        n AS (SELECT u, count(*) AS orders FROM d GROUP BY u),
        top AS (SELECT DISTINCT orders FROM n ORDER BY orders DESC LIMIT 3),
        pay AS (SELECT d.u, d.order_id, sum(p.payment_value) AS v, count(p.order_id) AS rows
                FROM d LEFT JOIN order_payments p USING (order_id) GROUP BY 1, 2),
        ranked AS (SELECT u, ts, city, state, row_number() OVER (PARTITION BY u ORDER BY ts DESC) AS rn,
                          count(*) OVER (PARTITION BY u, ts) AS same_ts FROM d)
        SELECT n.u AS customer_unique_id, n.orders AS delivered_orders, avg(pay.v) AS avg_payment_per_order,
               r.city, r.state, min(pay.rows) AS min_payment_rows, max(r.same_ts) AS ts_ties
        FROM n JOIN pay USING (u) JOIN ranked r ON r.u = n.u AND r.rn = 1
        WHERE n.orders IN (SELECT orders FROM top) GROUP BY n.u ORDER BY 2 DESC, 1""")
    assert (df.min_payment_rows > 0).all(), "a top customer has a delivered order without payments"
    assert (df.ts_ties == 1).all(), "most recent order is tied: city/state would be ambiguous"
    return df.drop(columns=["min_payment_rows", "ts_ties"])


_FUNNEL = """lead AS (SELECT mql_id, coalesce(nullif(origin, ''), 'unknown') AS channel FROM leads_qualified),
    won AS (SELECT l.channel, c.seller_id, c.won_date, coalesce(nullif(c.business_segment, ''), 'unknown') AS segment
            FROM leads_closed c JOIN lead l USING (mql_id)),
    sales AS (SELECT i.seller_id, i.order_id, i.price, cu.customer_unique_id AS u
              FROM order_items i JOIN orders o USING (order_id) JOIN customers cu USING (customer_id)
              WHERE o.order_status = 'delivered'),
    rev AS (SELECT seller_id, sum(price) AS revenue FROM sales GROUP BY 1)"""


def ce_channels(con) -> pd.DataFrame:
    return _sql(con, f"""WITH {_FUNNEL}
        SELECT l.channel, count(*) AS leads, count(c.mql_id) AS won, count(c.mql_id) * 100.0 / count(*) AS win_rate_pct
        FROM lead l LEFT JOIN leads_closed c USING (mql_id) GROUP BY 1 ORDER BY 2 DESC""")


def ce_active(con) -> pd.DataFrame:
    return _sql(con, f"""WITH {_FUNNEL}
        SELECT count(r.seller_id) AS active_sellers, count(r.seller_id) * 100.0 / count(*) AS active_pct
        FROM won w LEFT JOIN rev r USING (seller_id)""")


def ce_channel_sales(con) -> pd.DataFrame:
    return _sql(con, f"""WITH {_FUNNEL},
        ch AS (SELECT DISTINCT channel FROM lead),
        s AS (SELECT w.channel, count(DISTINCT s.seller_id) AS active_sellers, sum(s.price) AS revenue,
                     count(DISTINCT s.order_id) AS orders, count(DISTINCT s.u) AS customers
              FROM won w JOIN sales s USING (seller_id) GROUP BY 1)
        SELECT ch.channel, coalesce(s.active_sellers, 0) AS active_sellers, coalesce(s.revenue, 0) AS revenue,
               coalesce(s.orders, 0) AS orders, coalesce(s.customers, 0) AS customers
        FROM ch LEFT JOIN s USING (channel) ORDER BY 3 DESC, 1""")


def _won_revenue(con) -> pd.DataFrame:
    return _sql(con, f"""WITH {_FUNNEL}
        SELECT w.channel, w.seller_id, w.won_date, w.segment, coalesce(r.revenue, 0) AS revenue, r.seller_id IS NOT NULL AS active
        FROM won w LEFT JOIN rev r USING (seller_id)""")


def ce_seller_months(con) -> pd.DataFrame:
    w = _won_revenue(con)
    days = (pd.Timestamp(CUTOFF) - pd.to_datetime(w.won_date.str[:10])).dt.days
    w = w[days > 0].assign(rpm=w.revenue / (days[days > 0] / 30.44))
    g = w.groupby("channel").rpm
    return pd.DataFrame({"sellers": g.size(), "median_rpm": g.median(), "mean_rpm": g.mean()}).reset_index()


def ce_segments(con) -> pd.DataFrame:
    df = _sql(con, f"""WITH {_FUNNEL}
        SELECT w.segment, count(r.seller_id) AS active_sellers, coalesce(sum(r.revenue), 0) AS revenue
        FROM won w LEFT JOIN rev r USING (seller_id) GROUP BY 1 ORDER BY 3 DESC LIMIT 6""")
    assert df.revenue.iloc[4] - df.revenue.iloc[5] > 0.01, "tie at rank 5"
    return df.head(5)


def ce_costs(con) -> pd.DataFrame:
    df = ce_channels(con).merge(ce_channel_sales(con), on="channel")
    assert set(df.channel) == set(CPL), f"channels without a stated cost: {set(df.channel) ^ set(CPL)}"
    cost = df.channel.map(CPL) * df.leads
    return pd.DataFrame({"channel": df.channel, "lead_cost": cost, "cost_per_won": cost / df.won,
                         "cost_per_active": (cost / df.active_sellers.where(df.active_sellers > 0)),
                         "commission": df.revenue * COMMISSION,
                         "commission_pct_of_cost": df.revenue * COMMISSION * 100 / cost})


def ce_activation(con) -> pd.DataFrame:
    w = _won_revenue(con)
    extra = 0.0
    for _, g in w.groupby("channel"):
        active = g[g.active.astype(bool)]
        if active.empty:                        # no active seller → no median to apply
            continue
        add = max(0, math.floor(0.6 * len(g)) - len(active))
        extra += add * active.revenue.median() * COMMISSION
    return pd.DataFrame({"extra_commission": [extra]})


def _std(cols: list[int] | None = None) -> dict:
    return {"condition_cols": cols or [], "ignore_order": True}


PCT = "write percentages as percent with two decimals (12.34, not 0.1234)"

BUNDLES = {
    "olist-monthly-review": {
        "db": DB,
        "intro": f"""our marketplace's data from September 2016 to October 2018: orders, order items, payments, reviews, customers, products, sellers and seller leads.

We are preparing the monthly business review for August 2018, the last complete month: how sales are trending, what is selling, where our customers are, who our best customers are and how they pay.

For questions 3, 4 and 7:
- a customer is a `customer_unique_id` (`customer_id` is different on every order);
- count only orders with `order_status = 'delivered'`;
- revenue is the sum of `order_items.price` (freight excluded), in the month of `order_purchase_timestamp`;
- AOV is revenue divided by the number of delivered orders;
- {PCT}.""",
        "ids": [
            "local028",
            "local031",
            Question("olist_mr_q3", "For August 2018, July 2018 and August 2017: revenue, delivered orders, customers and "
                     "AOV. One row per month, with the month written as YYYY-MM.", mr_kpis, _std()),
            Question("olist_mr_q4", "The 10 product categories with the highest revenue from September 2017 to August 2018, "
                     "with their revenue and their share of that period's total revenue. Use the English category name; "
                     "if there is no translation use the Portuguese name, and group products without a category as "
                     "'unknown'.", mr_categories, _std()),
            "local030",
            "local004",
            Question("olist_mr_q7", "The customers whose number of delivered orders is among the three highest counts "
                     "(include every tied customer): their delivered orders, average payment per order (the sum of "
                     "`payment_value` of each delivered order, averaged over their delivered orders), and the city and "
                     "state of their most recent delivered order.", mr_top_customers, _std()),
        ],
    },
    "olist-channel-economics": {
        "db": DB,
        "intro": f"""our marketplace's data. We acquire sellers through marketing: `leads_qualified` has every marketing-qualified lead and its channel (`origin`), `leads_closed` has the leads we signed as sellers. Their sales are in the order tables; sales data ends {CUTOFF}.

We want to know which marketing channels bring sellers who actually sell, what those sellers sell, what each channel costs us per active seller, and what better activation would be worth.

Definitions:
- channel = `leads_qualified.origin`; an empty or missing origin counts as 'unknown';
- a won seller is a lead in `leads_closed`; an active seller is a won seller with at least one item in a delivered order (`order_status = 'delivered'`);
- seller revenue = sum of `order_items.price` on delivered orders;
- seller-months = days from the date of `won_date` to {CUTOFF}, divided by 30.44;
- cost per lead (R$, our planning assumptions): {", ".join(f"{k} {v}" for k, v in CPL.items())};
- our commission is {COMMISSION:.0%} of seller revenue;
- {PCT}; money in R$.""",
        "ids": [
            Question("olist_ce_q1", "Per channel: leads, won sellers and win rate.", ce_channels, _std()),
            Question("olist_ce_q2", "How many won sellers are active, and what percentage of won sellers is that?",
                     ce_active, _std()),
            Question("olist_ce_q3", "Per channel, including channels with no active sellers (as zeros): active sellers, "
                     "revenue, delivered orders and distinct customers (`customer_unique_id`).", ce_channel_sales, _std()),
            Question("olist_ce_q4", f"Per channel, for sellers won before {CUTOFF}: the number of sellers, and the median "
                     "and mean of revenue per seller-month (sellers with no sales count as 0).", ce_seller_months, _std()),
            Question("olist_ce_q5", "The 5 business segments (`leads_closed.business_segment`; missing counts as 'unknown') "
                     "with the highest revenue from their won sellers: active sellers and revenue.", ce_segments, _std()),
            Question("olist_ce_q6", "Per channel: total lead cost, cost per won seller, cost per active seller (empty if the "
                     "channel has none), commission revenue, and commission revenue as a percentage of lead cost.",
                     ce_costs, _std()),
            Question("olist_ce_q7", "If every channel's active sellers rose to 60% of its won sellers (rounded down to whole "
                     "sellers; channels already at or above that unchanged, channels with no active seller unchanged), and "
                     "each additional active seller earned that channel's median revenue per active seller, how much extra "
                     "commission revenue would we earn?", ce_activation, _std()),
        ],
    },
}
