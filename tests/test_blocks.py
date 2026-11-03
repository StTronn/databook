import json
from decimal import Decimal

import pytest

from conftest import block, results
from databook.cli import main
from databook.core.values import fmt


def _append(p, text):
    p.notebook.write_text(p.notebook.read_text() + "\n" + text + "\n")


def _codes(p):
    return [d["code"] for d in results(p)["diagnostics"]]


def _last_chart(p):
    return [b for b in results(p)["blocks"] if b["kind"] == "chart"][-1]


def test_titles_used_by_and_bad_fence(demo):
    t = demo.notebook.read_text().replace('```sql lost "Unpaid order value"', '```sql lost "Lost revenue"')
    demo.notebook.write_text(t)
    assert main(["check"]) == 0
    doc = results(demo)
    assert block(doc, "lost")["title"] == "Lost revenue" and block(doc, "methods")["title"] == "Payment methods"
    assert set(block(doc, "funnel")["usedBy"]) >= {"md_1", "kpi_1", "funnel_stages"}
    assert block(doc, "whatif")["usedBy"] == [b["id"] for b in doc["blocks"] if b["kind"] == "md"][-1:]
    _append(demo, "```sql untitled\nSELECT 1 AS x\n```")
    assert main(["check"]) == 0 and block(results(demo), "untitled")["title"] is None
    _append(demo, '```sql broken "unterminated\nSELECT 1\n```')
    assert main(["check"]) == 1 and "BAD_FENCE" in _codes(demo)


@pytest.mark.parametrize("spec, code", [
    ("{ type: pie, data: methods, x: method, y: [payments, succeeded] }", "BAD_SPEC"),
    ("{ type: bar, data: methods, x: method, y: payments, variant: wavy }", "BAD_SPEC"),
    ("{ type: donut, data: methods, x: method, y: payments }", "BAD_SPEC"),
    ("{ type: bar, data: methods, x: method, y: nope }", "CHART_COLUMN_MISSING"),
    ("{ type: bar, data: methods, x: method, y: method }", "CHART_NOT_NUMERIC"),
    ("{ type: radial, data: methods, y: success_rate }", "CHART_NEEDS_ONE_ROW"),
    ("{ type: radial, data: funnel, y: conv_paid, max: 0 }", "BAD_SPEC"),
    ("{ type: area, data: weekly, x: week, y: orders, variant: expanded }", "BAD_SPEC"),
    ("{ type: bar, data: weekly, x: week, y: [{col: orders, mark: bar}] }", "BAD_SPEC"),
    ("{ type: combo, data: weekly, x: week, y: [{col: orders, mark: pie}] }", "BAD_SPEC"),
    ("{ type: combo, data: weekly, x: week, y: [{col: orders, mark: band}] }", "BAD_SPEC"),
    ("{ type: combo, data: weekly, x: week, y: [{col: [orders, paid], mark: band}] }", "CHART_BAND_ORDER"),
    ("{ type: line, data: weekly, x: week, y: orders, zero: maybe }", "BAD_SPEC"),
])
def test_chart_spec_errors(demo, spec, code):
    _append(demo, f"```chart\n{spec}\n```")
    assert main(["check"]) == 1
    assert code in _codes(demo) and _last_chart(demo).get("error", "").startswith(code)


def test_duplicate_x(demo):
    _append(demo, "```sql dup\nSELECT * FROM (VALUES ('a', 1), ('a', 2), ('b', 3)) t(k, v)\n```\n"
                  "```chart\n{ type: bar, data: dup, x: k, y: v }\n```")
    assert main(["check"]) == 1 and "CHART_DUPLICATE_X" in _codes(demo)


def test_pie_negative_and_zero(demo):
    _append(demo, "```sql neg\nSELECT * FROM (VALUES ('a', 3), ('b', -1)) t(k, v)\n```\n"
                  "```chart\n{ type: pie, data: neg, x: k, y: v }\n```")
    assert main(["check"]) == 1 and "CHART_NEGATIVE" in _codes(demo)
    demo.notebook.write_text(demo.notebook.read_text().replace("('a', 3), ('b', -1)", "('a', 0), ('b', 0)"))
    assert main(["check"]) == 1 and "sum to 0" in _last_chart(demo)["error"]


def test_chart_outputs(demo):
    _append(demo, "```chart\n{ type: hbar, data: failures, x: reason, y: failed_payments }\n```\n"
                  "```chart\n{ type: radial, data: funnel, y: conv_paid, format: pct, variant: text }\n```\n"
                  "```chart\n{ type: pie, data: methods, x: method, y: lost_inr, format: inr, variant: donut-text }\n```\n"
                  "```chart\n{ type: combo, data: weekly, x: week, y: [{col: orders, mark: bar}, "
                  "{col: paid, mark: line, label: Paid}, {col: [paid, orders], mark: band}] }\n```")
    assert main(["check"]) == 0
    doc = results(demo)
    hbar, radial, pie, combo = [b for b in doc["blocks"] if b["kind"] == "chart"][-4:]
    assert (hbar["type"], hbar["variant"]) == ("bar", "horizontal")
    f = block(doc, "funnel")
    assert radial["max"] == 1 and radial["series"][0]["display"] == [f["display"][0][-1]]
    m = block(doc, "methods")
    assert pie["total"] == fmt(sum(Decimal(r[-1]) for r in m["rows"]), "inr")
    assert pie["series"][0]["display"][0].startswith("₹")
    funnel = next(b for b in doc["blocks"] if b["kind"] == "chart" and b["type"] == "funnel")
    assert funnel["share"][0] == "100.0%" and funnel["share"][2] == f["display"][0][-1]
    assert [s.get("mark") for s in combo["series"]] == ["bar", "line", "band"]
    assert combo["zero"] is True and hbar["zero"] is True
    assert combo["series"][1]["name"] == "Paid" and " – " in combo["series"][2]["display"][0]
    w = block(doc, "weekly")
    assert combo["series"][2]["values"] == [float(r[2]) for r in w["rows"]]
    assert combo["series"][2]["values2"] == [float(r[1]) for r in w["rows"]]


def test_components_command(capsys):
    assert main(["--json", "components", "combo"]) == 0
    d = json.loads(capsys.readouterr().out)
    assert list(d["chart"]) == ["combo"] and "band" in d["chart"]["combo"]["marks"]
    assert main(["components", "nope"]) == 2


def test_diff_between_runs(demo, capsys):
    assert main(["check"]) == 0
    assert main(["check"]) == 0                                   # identical rerun collapses into the same entry
    assert len(list(demo.nb().history_dir.glob("*.json"))) == 1
    t = demo.notebook.read_text()
    t = t.replace("WHERE o.currency = 'INR'\n```", "WHERE o.currency = 'INR' AND o.amount > 500\n```")
    t = t.replace("```sql aov ", "```sql aov2\nSELECT 1 AS one\n```\n\n```sql aov ")
    t = t.replace("SELECT payments, success_rate FROM methods WHERE method = 'card'", "SELECT nope FROM methods")
    demo.notebook.write_text(t)
    main(["check"])
    capsys.readouterr()
    assert main(["--json", "diff"]) == 0
    ch = {c["key"]: c for c in json.loads(capsys.readouterr().out)["changes"]}
    assert ch["funnel"]["change"] == "~" and "code edited" in ch["funnel"]["details"]
    assert any(d.startswith("created: ") for d in ch["funnel"]["details"])
    assert ch["kpi Orders"]["change"] == "~" and ch["{{funnel.created}}"]["change"] == "~"
    assert ch["aov2"]["change"] == "+"
    assert ch["card"]["change"] == "!" and ch["whatif"]["change"] == "!"
    assert "lost" not in ch                                       # unaffected block → no entry
