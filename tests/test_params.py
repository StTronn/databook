"""Notebook parameters: frontmatter `params:`, `$name` in SQL, `params` in Python, picked values, table links."""
import json

import pytest

from databook.cli import main
from databook.core.notebook import bind_params, sql_params
from databook.project import Project
from databook.run import run_notebook

HEAD = """---
params:
  cust: {from: custs.id, show: custs.name, default: 2, label: Customer}
---
```sql custs
SELECT id, name FROM people
```

```sql spend
SELECT sum(amount) AS total, count(*) AS n FROM orders WHERE customer = $cust
```
"""


@pytest.fixture
def ws(tmp_path, monkeypatch):
    root = tmp_path / "ws"
    assert main(["init", str(root), "--tz", "UTC"]) == 0
    monkeypatch.chdir(root)
    (root / "notebooks" / "untitled.md").unlink()
    (root / "people.csv").write_text("id,name\n1.0,Ann\n2.0,Bo\n3.0,Cy\n")      # DOUBLE ids, like an Excel import
    (root / "orders.csv").write_text("customer,amount\n1,10\n2,5\n2,7\n3,1\n")
    assert main(["import", "people.csv", "--name", "people"]) == 0
    assert main(["import", "orders.csv", "--name", "orders"]) == 0
    return Project(root)


def run(ws, text, key="nb"):
    (ws.root / "notebooks" / f"{key}.md").write_text(text)
    return run_notebook(ws, key)


def block(doc, bid):
    return next(b for b in doc["blocks"] if b["id"] == bid)


def codes(doc):
    return [d["code"] for d in doc["diagnostics"]]


def test_exact_match_for_big_ids():
    from databook.run import _same
    big = 2 ** 53 + 1
    assert _same(big, str(big)) and not _same(big, str(big - 1)) and _same(2.0, 2) and not _same(2, True)


def test_sql_params_skip_strings_comments_and_positional():
    sql = "SELECT '$x', $a AS c, $$q $y$$ AS d, n-$b FROM t WHERE id=$a -- $z"
    assert [n for *_, n in sql_params(sql)] == ["a", "b", "a"]
    assert bind_params(sql) == ("SELECT '$x', getvariable('a') AS c, $$q $y$$ AS d, n-getvariable('b') FROM t "
                                "WHERE id=getvariable('a') -- $z")


def test_default_then_picked_value_drive_the_result(ws):
    doc = run(ws, HEAD)
    assert doc["ok"], doc["diagnostics"]
    (p,) = doc["params"]
    assert (p["name"], p["label"], p["value"], p["display"]) == ("cust", "Customer", "2.0", "Bo")
    assert p["options"] == [["1.0", "Ann"], ["2.0", "Bo"], ["3.0", "Cy"]]   # DECIMAL: exact strings
    assert block(doc, "spend")["rows"] == [[12, 2]] and "custs" in block(doc, "spend")["deps"]
    ws.save_params("nb", {"cust": 1})                 # integer picked, DOUBLE option: still the same customer
    doc2 = run_notebook(ws, "nb")
    assert doc2["params"][0]["display"] == "Ann" and block(doc2, "spend")["rows"] == [[10, 1]]
    assert doc2["dataHash"] != doc["dataHash"]        # history tells the two picks apart


def test_stale_pick_and_bad_default_fall_back_with_warnings(ws):
    (ws.root / "notebooks" / "nb.md").write_text(HEAD)
    ws.save_params("nb", {"cust": 99})
    doc = run_notebook(ws, "nb")
    assert "PARAM_VALUE_MISSING" in codes(doc) and doc["params"][0]["display"] == "Bo" and doc["ok"]
    doc = run(ws, HEAD.replace("default: 2", "default: 42"))
    assert {"PARAM_VALUE_MISSING", "PARAM_DEFAULT_MISSING"} <= set(codes(doc)) and doc["params"][0]["display"] == "Ann"


def test_text_options_match_exactly_not_numerically(ws):
    nb = HEAD.replace("SELECT id, name FROM people", "SELECT '00' || id::INT AS id, name FROM people").replace(
        "default: 2", "default: '002'").replace("WHERE customer = $cust", "WHERE '00' || customer = $cust")
    doc = run(ws, nb)
    assert doc["params"][0]["value"] == "002" and block(doc, "spend")["rows"] == [[12, 2]]
    ws.save_params("nb", {"cust": 2})                 # 2 is not the text "002"
    assert "PARAM_VALUE_MISSING" in codes(run_notebook(ws, "nb"))


def test_python_blocks_get_params(ws):
    doc = run(ws, HEAD + "\n```python one\nreturn pd.DataFrame({'picked': [params['cust']]})\n```\n")
    assert doc["ok"], doc["diagnostics"]
    assert block(doc, "one")["rows"] == [["2.0"]]
    assert "custs" in block(doc, "one")["deps"]


def test_errors_unknown_param_self_reference_and_bad_spec(ws):
    doc = run(ws, HEAD.replace("$cust", "$other"))
    assert "PARAM_UNKNOWN" in codes(doc) and not doc["ok"]
    doc = run(ws, HEAD.replace("SELECT id, name FROM people", "SELECT id, name FROM people WHERE id <> $cust"))
    assert "CYCLE" in codes(doc) and not doc["ok"]
    for bad in ("cust: {from: nope.id}", "cust: {from: custs}", "Cust: {from: custs.id}",
                "cust: {from: custs.id, show: spend.n}"):
        doc = run(ws, HEAD.replace("cust: {from: custs.id, show: custs.name, default: 2, label: Customer}", bad))
        assert "BAD_PARAM" in codes(doc), bad
    doc = run(ws, HEAD.replace("custs.id, show", "custs.missing, show"))
    assert "BAD_PARAM" in codes(doc) and block(doc, "spend")["status"] == "skipped"


def test_table_link_lists_values_to_pick(ws):
    tbl = "\n```table\n{ data: custs, columns: [name, id], link: { column: id, param: cust } }\n```\n"
    doc = run(ws, HEAD + tbl)
    assert block(doc, "table_1")["link"] == {"column": "id", "param": "cust", "values": ["1.0", "2.0", "3.0"]}
    doc = run(ws, HEAD + tbl.replace("param: cust", "param: nope"))
    assert "BAD_SPEC" in codes(doc)


def test_cli_param_stores_pick(ws, capsys):
    (ws.root / "notebooks" / "nb.md").write_text(HEAD)
    assert main(["param", "cust=3"]) == 0
    assert json.loads(ws.nb("nb").params_path.read_text()) == {"cust": 3}
    assert main(["check"]) == 0
    capsys.readouterr()
    assert main(["param"]) == 0
    assert "cust = 3  (last run used Cy)" in capsys.readouterr().out


def test_export_ships_the_picked_value_not_the_option_list(ws, tmp_path):
    (ws.root / "notebooks" / "nb.md").write_text(HEAD)
    assert main(["export", str(tmp_path / "r.html")]) == 0
    html = (tmp_path / "r.html").read_text()
    assert '"display": "Bo", "options": []' in html          # the options block's own rows still show as usual
