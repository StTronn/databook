import json
from datetime import datetime, date
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from conftest import FIX
from databook.cli import main
from databook.ingest import types as T

IST = ZoneInfo("Asia/Kolkata")


def test_real_razorpay_samples_import_exactly(project):
    files = sorted(str(f) for f in (FIX / "razorpay").glob("*.xlsx"))
    assert main(["import", *files]) == 0
    m = project.manifest["tables"]
    assert {k: v["source"] for k, v in m.items()} == {
        "payments": "razorpay.payments", "orders": "razorpay.orders", "refunds": "razorpay.refunds",
        "settlements": "razorpay.settlements", "combined": "razorpay.combined",
        "settlement_recon": "razorpay.recon", "subscriptions": "razorpay.subscriptions"}
    con = project.connect(read_only=True)
    # contact cells are `=+9199…` formulas: cached value, kept as text (not BIGINT)
    assert con.execute("SELECT DISTINCT contact FROM payments").fetchall() == [("919900990099",)]
    assert con.execute("SELECT typeof(contact), typeof(amount), typeof(captured) FROM payments LIMIT 1").fetchone() \
        == ("VARCHAR", "DECIMAL(18,2)", "BOOLEAN")
    # orders.created_at is text "04/07/2022 11:31:23": day-first, IST
    assert con.execute("SELECT created_at FROM orders WHERE id = 'order_JpBNrbnn239zXK'").fetchone()[0] \
        == datetime(2022, 7, 4, 11, 31, 23, tzinfo=IST)
    assert con.execute("SELECT amount FROM orders WHERE id = 'order_JpBNrbnn239zXK'").fetchone()[0] == Decimal("12.00")
    # settlements: blank column A and trailing blank rows
    assert con.execute("SELECT id, amount FROM settlements").fetchall() == [("setl_K4eBPTyLTnLCGr", Decimal("1.91"))]
    # subscriptions export crashes plain openpyxl (pageMargins left=""); sanitized here
    assert con.execute("SELECT count(*) FROM subscriptions").fetchone()[0] == 3
    # refunds.arn is digits-only but an identifier
    assert con.execute("SELECT typeof(arn) FROM refunds LIMIT 1").fetchone()[0] == "VARCHAR"


def test_json_minor_units_and_unix(project, tmp_path):
    f = tmp_path / "payments.json"
    f.write_text(json.dumps({"entity": "collection", "count": 3, "items": [
        {"id": "pay_1", "entity": "payment", "amount": 50000, "currency": "INR", "status": "captured",
         "captured": True, "method": "upi", "order_id": "order_1", "created_at": 1756455622, "notes": {"a": 1}},
        {"id": "pay_2", "entity": "payment", "amount": 1500, "currency": "JPY", "status": "captured",
         "captured": True, "method": "card", "order_id": None, "created_at": 1756455622, "notes": []},
        {"id": "pay_1", "entity": "payment", "amount": 50000, "currency": "INR", "status": "captured",
         "captured": True, "method": "upi", "order_id": "order_1", "created_at": 1756455622, "notes": {"a": 1}}]}))
    assert main(["import", str(f)]) == 0
    con = project.connect(read_only=True)
    rows = con.execute("SELECT id, amount, created_at, notes FROM payments ORDER BY id").fetchall()
    assert rows[0][:2] == ("pay_1", Decimal("500.00"))       # paise → rupees, duplicate pay_1 dropped
    assert rows[1][1] == Decimal("1500.00")                  # JPY has no minor unit
    assert rows[0][2] == datetime(2025, 8, 29, 8, 20, 22, tzinfo=ZoneInfo("UTC"))
    assert json.loads(rows[0][3]) == {"a": 1}
    assert len(rows) == 2


def test_three_decimal_currency_refused(project, tmp_path):
    f = tmp_path / "p.json"
    f.write_text(json.dumps([{"id": "pay_1", "entity": "payment", "amount": 1234, "currency": "KWD",
                              "status": "captured", "created_at": 1756455622}]))
    assert main(["import", str(f)]) == 1
    assert "payments" not in project.manifest["tables"]


def test_generic_csv_inference(project, tmp_path):
    f = tmp_path / "sales.csv"
    f.write_text("Deal Name,Amount,Pincode,When,Closed\nAcme,\"1,82,200.50\",011001,2026-05-01,true\n"
                 "Beta,950,560001,2026-05-02 10:00,false\n")
    assert main(["import", str(f)]) == 0
    cols = {c["name"]: c["type"] for c in project.manifest["tables"]["sales"]["columns"]}
    assert cols == {"deal_name": "VARCHAR", "amount": "DECIMAL(18,2)", "pincode": "VARCHAR",
                    "when": "TIMESTAMP", "closed": "BOOLEAN"}
    con = project.connect(read_only=True)
    assert con.execute("SELECT sum(amount) FROM sales").fetchone()[0] == Decimal("183150.50")


def test_ambiguous_dates_require_override(project, tmp_path):
    f = tmp_path / "d.csv"
    f.write_text("id,day\n1,05/07/2022\n2,06/08/2022\n")
    assert main(["import", str(f)]) == 1                          # AMBIGUOUS_DATE, nothing loaded
    assert "d" not in project.manifest["tables"]
    assert main(["import", str(f), "--types", "day=date:mdy"]) == 0
    con = project.connect(read_only=True)
    assert con.execute("SELECT day FROM d ORDER BY id").fetchall()[0][0] == datetime(2022, 5, 7)


@pytest.mark.parametrize("values,expected", [
    (["13/05/2022", "01/06/2022"], "date:dmy"),
    (["05/13/2022", "06/01/2022"], "date:mdy"),
    (["13/05/2022", "05/13/2022"], "text"),
    (["007", "12"], "text"),
    (["=SUM(A1)", "1"], "text"),
    ([1, 2.0, "3"], "int"),
    (["1.5", "2.25"], "decimal:2"),
    ([0.1 + 0.2], "double"),
    ([1, "x"], "text"),
    ([True, False], "bool"),
    ([datetime(2022, 1, 1), date(2022, 1, 2)], "timestamp"),
    (["2022-01-01T10:00:00+05:30"], "tz_timestamp"),
])
def test_infer(values, expected):
    assert T.infer(values)[0] == expected


def test_infer_refuses_guesses():
    with pytest.raises(T.Ambiguous) as e:
        T.infer(["05/07/2022"])
    assert e.value.code == "AMBIGUOUS_DATE"
    with pytest.raises(T.Ambiguous) as e:
        T.infer(["1.234,56"])
    assert e.value.code == "AMBIGUOUS_NUMBER"


def test_decimal_converter_never_rounds():
    conv = T.named("decimal:2")[1]
    assert conv(0.99, None) == "0.99"
    assert conv("₹1,200", None) == "1200.00"
    with pytest.raises(ValueError):
        conv("1.005", None)


def test_unknown_source_and_forced_pack(project, tmp_path):
    f = tmp_path / "x.csv"
    f.write_text("id,amount,currency,status,created_at\np1,5,INR,captured,01/02/2022 10:00:00\n")
    assert main(["import", str(f), "--as", "razorpay.nope"]) == 1
    assert main(["import", str(f), "--as", "razorpay.payments"]) == 0
    assert project.manifest["tables"]["payments"]["source"] == "razorpay.payments"


def test_sqlite_tables_import_by_name(project, tmp_path):
    import sqlite3
    f = tmp_path / "shop.sqlite"
    con = sqlite3.connect(f)
    con.executescript("""CREATE TABLE "Web Log"(stamp TEXT, session TEXT, n INT, raw BLOB);
        INSERT INTO "Web Log" VALUES ('2016-12-30 00:56:08','a',1,x'ff'),('2016-12-30 00:57:04','a',NULL,NULL);
        CREATE TABLE empty_t(a TEXT);""")
    con.commit(); con.close()
    assert main(["import", str(f)]) == 0
    t = project.manifest["tables"]
    assert set(t) == {"web_log", "empty_t"} and t["web_log"]["rows"] == 2 and t["empty_t"]["rows"] == 0
    assert {c["name"]: c["type"] for c in t["web_log"]["columns"]} == \
        {"stamp": "TIMESTAMP", "session": "VARCHAR", "n": "BIGINT", "raw": "VARCHAR"}
    con = project.connect(read_only=True)
    assert con.execute("SELECT raw, n FROM web_log ORDER BY stamp").fetchall() == [("ff", 1), (None, None)]
    con.close()


def test_export_block_csv(project, tmp_path):
    (project.root / "t.csv").write_text("session,path\na,/x\nb,/x\na,/y\n")
    assert main(["import", "t.csv", "--name", "t"]) == 0
    nb = project.nb().path
    nb.write_text('```sql v\nSELECT path, count(DISTINCT session) AS n FROM t GROUP BY 1 ORDER BY 1\n```\n')
    out = tmp_path / "a.csv"
    assert main(["export", "--block", "v", str(out)]) == 0
    assert out.read_text() == "path,n\n/x,2\n/y,1\n"
    assert main(["export", "--block", "nope", str(out)]) != 0
    nb.write_text('```sql v\nSELECT nope FROM t\n```\n')
    assert main(["export", "--block", "v", str(out)]) == 1          # refuses while check has errors
