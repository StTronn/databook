"""Olist bundles: every gold recomputed independently in pandas (no shared SQL) and graded with the task's own compare.py.
Also checks Spider2's golds (made on `Brazilian_E_Commerce`) hold on `E_commerce`, the db the tasks ship.
Needs the fetched Spider2 cache (fetch.sh … local028 local030 local031 local004); skipped otherwise."""
import math
import sqlite3
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "adapters" / "spider2-lite" / "src"))
from spider2_lite import adapter, compare, olist  # noqa: E402

DB = adapter.CACHE / "localdb" / f"{olist.DB}.sqlite"
pytestmark = pytest.mark.skipif(not DB.exists(), reason="Spider2 cache not fetched")


@pytest.fixture(scope="module")
def t():
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    names = ["orders", "customers", "order_items", "order_payments", "products", "product_category_name_translation",
             "leads_qualified", "leads_closed"]
    yield {n: pd.read_sql_query(f"SELECT * FROM {n}", con) for n in names} | {"con": con}
    con.close()


def _delivered(t):
    o = t["orders"]
    return o[o.order_status == "delivered"].merge(t["customers"], on="customer_id")


def _channels(t):
    lq = t["leads_qualified"].copy()
    lq["channel"] = lq.origin.replace("", None).fillna("unknown")
    won = t["leads_closed"].merge(lq[["mql_id", "channel"]], on="mql_id")
    sales = t["order_items"].merge(_delivered(t), on="order_id")
    rev = sales.groupby("seller_id").price.sum()
    won["revenue"] = won.seller_id.map(rev)
    return lq, won, sales


def pd_mr_q3(t):
    x = t["order_items"].merge(_delivered(t), on="order_id")
    x["month"] = x.order_purchase_timestamp.str[:7]
    g = x[x.month.isin(["2017-08", "2018-07", "2018-08"])].groupby("month")
    r = pd.DataFrame({"revenue": g.price.sum(), "orders": g.order_id.nunique(), "customers": g.customer_unique_id.nunique()})
    return r.assign(aov=r.revenue / r.orders).reset_index()


def pd_mr_q4(t):
    x = t["order_items"].merge(_delivered(t), on="order_id").merge(t["products"], on="product_id", how="left")
    x = x[(x.order_purchase_timestamp >= "2017-09-01") & (x.order_purchase_timestamp < "2018-09-01")]
    x = x.merge(t["product_category_name_translation"], on="product_category_name", how="left")
    x["category"] = x.product_category_name_english.fillna(x.product_category_name.replace("", None)).fillna("unknown")
    r = x.groupby("category").price.sum()
    return pd.DataFrame({"revenue": r, "share": r * 100 / r.sum()}).nlargest(10, "revenue").reset_index()


def pd_mr_q7(t):
    d = _delivered(t)
    n = d.groupby("customer_unique_id").size()
    top = n[n.isin(sorted(n.unique(), reverse=True)[:3])]
    per_order = d[["order_id", "customer_unique_id"]].merge(
        t["order_payments"].groupby("order_id").payment_value.sum().rename("v").reset_index(), on="order_id")
    last = d.sort_values("order_purchase_timestamp").groupby("customer_unique_id").last()
    return pd.DataFrame({"orders": top, "avg_pay": per_order.groupby("customer_unique_id").v.mean().reindex(top.index),
                         "city": last.customer_city.reindex(top.index),
                         "state": last.customer_state.reindex(top.index)}).reset_index()


def pd_local028(t):
    o = t["orders"]
    o = o[(o.order_status == "delivered") & o.order_delivered_customer_date.notna()]
    ts = pd.to_datetime(o.order_delivered_customer_date)
    p = pd.crosstab(ts.dt.month, ts.dt.year).reindex(index=range(1, 13), columns=[2016, 2017, 2018], fill_value=0)
    return p.reset_index()


def pd_local031(t):
    p = pd_local028(t).set_index("order_delivered_customer_date")
    return pd.DataFrame({"v": [p[p.sum().idxmin()].max()]})


def pd_local030(t):
    x = _delivered(t).merge(t["order_payments"], on="order_id")
    g = x.groupby("customer_city").agg(pay=("payment_value", "sum"), n=("order_id", "nunique")).nsmallest(5, "pay")
    return pd.DataFrame({"pay": [g.pay.mean()], "n": [g.n.mean()]})


def pd_local004(t):
    x = t["orders"].merge(t["customers"], on="customer_id").merge(
        t["order_payments"].groupby("order_id").payment_value.sum().rename("v").reset_index(), on="order_id")
    g = x.groupby("customer_unique_id").agg(n=("order_id", "nunique"), avg=("v", "mean"),
                                            first=("order_purchase_timestamp", "min"), last=("order_purchase_timestamp", "max"))
    g = g.nlargest(3, "avg")
    weeks = (pd.to_datetime(g["last"]) - pd.to_datetime(g["first"])).dt.days / 7
    return g.assign(weeks=weeks.where(weeks >= 1, 1.0))[["n", "avg", "weeks"]].reset_index()


def pd_ce_q1(t):
    lq, won, _ = _channels(t)
    r = pd.DataFrame({"leads": lq.groupby("channel").size(), "won": won.groupby("channel").size()}).fillna(0)
    return r.assign(rate=r.won * 100 / r.leads).reset_index()


def pd_ce_q2(t):
    _, won, _ = _channels(t)
    return pd.DataFrame({"active": [won.revenue.notna().sum()], "pct": [won.revenue.notna().mean() * 100]})


def pd_ce_q3(t):
    lq, won, sales = _channels(t)
    x = won[["seller_id", "channel"]].merge(sales, on="seller_id")
    g = x.groupby("channel")
    r = pd.DataFrame({"active": g.seller_id.nunique(), "revenue": g.price.sum(), "orders": g.order_id.nunique(),
                      "customers": g.customer_unique_id.nunique()}).reindex(lq.channel.unique(), fill_value=0)
    return r.rename_axis("channel").reset_index()


def pd_ce_q4(t):
    _, won, _ = _channels(t)
    days = (pd.Timestamp(olist.CUTOFF) - pd.to_datetime(won.won_date).dt.normalize()).dt.days
    w = won[days > 0].assign(rpm=won.revenue.fillna(0) / (days / 30.44))
    g = w.groupby("channel").rpm
    return pd.DataFrame({"n": g.size(), "median": g.median(), "mean": g.mean()}).reset_index()


def pd_ce_q5(t):
    _, won, _ = _channels(t)
    won["segment"] = won.business_segment.replace("", None).fillna("unknown")
    g = won.groupby("segment")
    return pd.DataFrame({"active": g.revenue.count(), "revenue": g.revenue.sum()}).nlargest(5, "revenue").reset_index()


def pd_ce_q6(t):
    x = pd_ce_q1(t).merge(pd_ce_q3(t), on="channel")
    cost = x.channel.map(olist.CPL) * x.leads
    return pd.DataFrame({"channel": x.channel, "cost": cost, "per_won": cost / x.won,
                         "per_active": [c / a if a else None for c, a in zip(cost, x.active)],
                         "commission": x.revenue * 0.1, "pct": x.revenue * 0.1 * 100 / cost})


def pd_ce_q7(t):
    _, won, _ = _channels(t)
    total = 0.0
    for _, g in won.groupby("channel"):
        act = g.revenue.dropna()
        if len(act):
            total += max(0, math.floor(0.6 * len(g)) - len(act)) * act.median() * 0.1
    return pd.DataFrame({"x": [total]})


OURS = {"olist_mr_q3": pd_mr_q3, "olist_mr_q4": pd_mr_q4, "olist_mr_q7": pd_mr_q7, "olist_ce_q1": pd_ce_q1,
        "olist_ce_q2": pd_ce_q2, "olist_ce_q3": pd_ce_q3, "olist_ce_q4": pd_ce_q4, "olist_ce_q5": pd_ce_q5,
        "olist_ce_q6": pd_ce_q6, "olist_ce_q7": pd_ce_q7}
SPIDER = {"local028": pd_local028, "local031": pd_local031, "local030": pd_local030, "local004": pd_local004}
QUESTIONS = {q.id: q for b in olist.BUNDLES.values() for q in b["ids"] if isinstance(q, olist.Question)}


def test_every_question_has_a_check():
    spider = {i for b in olist.BUNDLES.values() for i in b["ids"] if isinstance(i, str)}
    assert set(QUESTIONS) == set(OURS) and spider == set(SPIDER)


@pytest.mark.parametrize("qid", sorted(OURS))
def test_reference_gold_matches_independent_pandas(qid, t, tmp_path):
    (tmp_path / "gold").mkdir()
    QUESTIONS[qid].gold(t["con"]).to_csv(tmp_path / "gold" / f"{qid}.csv", index=False)
    OURS[qid](t).to_csv(tmp_path / "pred.csv", index=False)
    assert compare.score(tmp_path / "pred.csv", tmp_path / "gold", qid, QUESTIONS[qid].standard) == (1, "match")


@pytest.mark.parametrize("iid", sorted(SPIDER))
def test_spider2_gold_holds_on_shipped_db(iid, t, tmp_path):
    std = {k: v for k, v in adapter._jsonl(adapter.CACHE / "spider2lite_eval.jsonl")[iid].items()
           if k in ("condition_cols", "ignore_order")}
    SPIDER[iid](t).to_csv(tmp_path / "pred.csv", index=False)
    assert compare.score(tmp_path / "pred.csv", adapter.CACHE / "gold", iid, std) == (1, "match")


@pytest.mark.parametrize("name", sorted(olist.BUNDLES))
def test_bundle_builds_and_oracle_scores_full(name, tmp_path):
    d = adapter.make_bundle(name, tmp_path)
    qs = __import__("json").loads((d / "tests" / "bundle.json").read_text())["questions"]
    for q, iid in qs.items():
        std = __import__("json").loads((d / "tests" / f"eval_{iid}.json").read_text())
        assert compare.score(d / "solution" / "answers" / f"{q}.csv", d / "tests" / "gold", iid, std)[0] == 1, q
    text = (d / "instruction.md").read_text()
    assert f"/app/data/{olist.DB}.sqlite" in text and f"`/app/answers/q{len(qs)}.csv`" in text
