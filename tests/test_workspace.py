import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

import duckdb

import pytest

from tracebook import workspace
from tracebook.cli import main
from tracebook.packs import templates
from tracebook.project import Project, ProjectError


@pytest.fixture
def ws(tmp_path, monkeypatch):
    """Workspace with one imported table `t` (k text, v int) and no notebooks."""
    root = tmp_path / "ws"
    assert main(["init", str(root), "--tz", "UTC"]) == 0
    monkeypatch.chdir(root)
    (root / "notebooks" / "untitled.md").unlink()
    (root / "t.csv").write_text("k,v\na,1\nb,2\na,3\n")
    assert main(["import", "t.csv", "--name", "t"]) == 0
    return Project(root)


def _nb(p, key, body):
    f = p.root / "notebooks" / f"{key}.md"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(body)


def _res(p, key):
    return json.loads(p.nb(key).results_path.read_text())


def _blk(doc, bid):
    return next(b for b in doc["blocks"] if b["id"] == bid)


def test_same_block_id_in_two_notebooks_is_isolated(ws):
    _nb(ws, "a", "```sql s\nSELECT sum(v) AS n FROM t\n```\n")
    _nb(ws, "growth/b", "```sql s\nSELECT count(*) AS n FROM t WHERE k = 'a'\n```\n```sql s2\nSELECT n * 10 AS m FROM s\n```\n")
    assert main(["check"]) == 0
    assert _blk(_res(ws, "a"), "s")["rows"] == [[6]]
    b = _res(ws, "growth/b")
    assert _blk(b, "s")["rows"] == [[2]] and _blk(b, "s2")["rows"] == [[20]] and b["notebook"] == "growth/b"
    assert _blk(_res(ws, "a"), "s")["reads"] == ["t"]


def test_block_named_like_imported_table_never_drops_it(ws):
    _nb(ws, "a", "```sql t\nSELECT 1 AS x\n```\n")
    assert main(["check"]) == 1
    con = ws.connect(read_only=True)
    assert con.execute("SELECT count(*) FROM main.t").fetchone()[0] == 3        # regression: used to be dropped


def test_removed_notebook_drops_its_schema(ws):
    _nb(ws, "a", "```sql s\nSELECT 1 AS x\n```\n")
    _nb(ws, "gone", "```sql s\nSELECT 2 AS x\n```\n")
    assert main(["check"]) == 0
    (ws.root / "notebooks" / "gone.md").unlink()
    assert main(["check"]) == 0
    con = ws.connect(read_only=True)
    schemas = {s for (s,) in con.execute("SELECT schema_name FROM duckdb_schemas()").fetchall()}
    assert "nb_a" in schemas and "nb_gone" not in schemas


def test_cross_notebook_reference_is_rejected(ws):
    _nb(ws, "a", "```sql s\nSELECT 1 AS x\n```\n")
    _nb(ws, "b", "```sql r\nSELECT * FROM nb_a.s\n```\n")
    assert main(["check"]) == 1
    assert [d["code"] for d in _res(ws, "b")["diagnostics"]] == ["CROSS_NOTEBOOK_REF"]


def test_commands_need_a_notebook_when_several(ws, capsys):
    _nb(ws, "a", "```sql s\nSELECT 1 AS x\n```\n")
    _nb(ws, "b", "```sql s\nSELECT 2 AS x\n```\n")
    assert main(["check", "--nb", "b"]) == 0
    assert main(["export"]) == 2 and "several notebooks" in capsys.readouterr().err
    assert main(["export", "--nb", "a"]) == 0 and (ws.root / "dist" / "a.html").exists()
    assert main(["query", "SELECT x FROM s", "--nb", "b"]) == 0 and "2" in capsys.readouterr().out
    with pytest.raises(ProjectError):
        ws.nb("nope")


def test_new_notebook_names_and_templates(ws, capsys):
    for bad in ("../x", "a b", "/abs", "x/../../y", ""):
        assert main(["new", bad]) == 2
    assert main(["new", "growth/cohort-a"]) == 0
    assert (ws.root / "notebooks" / "growth" / "cohort-a.md").read_text().startswith("---\ntitle: Cohort a")
    assert main(["new", "growth/cohort-a"]) == 2                                 # exists
    assert main(["new", "growth/cohort_a"]) == 2                                 # same schema name
    (ws.root / "models").mkdir()
    (ws.root / "models" / "whatif.xlsx").write_bytes(b"mine")
    capsys.readouterr()
    assert main(["--json", "new", "rzp", "--template", "razorpay-funnel"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["skipped"] == ["models/whatif.xlsx"] and (ws.root / "models" / "whatif.xlsx").read_bytes() == b"mine"
    assert (ws.root / "notebooks" / "rzp.md").read_text() == (templates()["razorpay-funnel"] / "notebook.md").read_text()


def test_bad_notebook_file_name_is_reported(ws):
    _nb(ws, "ok", "# hi\n")
    (ws.root / "notebooks" / "my notes.md").write_text("# x\n")
    with pytest.raises(ProjectError, match="unsupported name"):
        ws.notebooks()


def test_legacy_root_notebook_is_a_notebook(ws):
    (ws.root / "notebook.md").write_text("```sql s\nSELECT 1 AS x\n```\n")
    _nb(ws, "other", "# other\n")
    assert list(ws.notebooks()) == ["notebook", "other"]
    assert main(["check"]) == 0


def test_schema_and_preview(ws):
    _nb(ws, "a", "```sql s\nSELECT k, sum(v) AS n FROM t GROUP BY k\n```\n")
    assert main(["check"]) == 0
    sc = workspace.schema(ws)["tables"]
    assert [t["name"] for t in sc] == ["t"] and sc[0]["usedBy"] == [{"notebook": "a", "block": "s"}]
    assert next(c for c in sc[0]["columns"] if c["name"] == "k")["values"] == ["a", "b"]
    pv = workspace.preview(ws, "t", limit=2)
    assert pv["rowCount"] == 3 and len(pv["rows"]) == 2 and pv["truncated"]
    for bad in ("s", "nb_a.s", 't"; DROP TABLE t; --'):
        with pytest.raises(ProjectError):
            workspace.preview(ws, bad)
    info = workspace.info(ws)
    assert info["notebooks"][0] == {**info["notebooks"][0], "key": "a", "ok": True, "errors": 0}
    assert info["settings"]["engines"]["duckdb"]


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _req(url, data=None, headers=None):
    r = urllib.request.Request(url, data=data, headers=headers or {}, method="POST" if data is not None else "GET")
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            return resp.status, json.loads(resp.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")


def test_dev_server_api_and_guards(ws):
    _nb(ws, "a", "```sql s\nSELECT 1 AS x\n```\n")
    port = _free_port()
    proc = subprocess.Popen([sys.executable, "-m", "tracebook.cli", "dev", "--port", str(port)], cwd=ws.root,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                if _req(f"{base}/version")[1]["version"] >= 1:
                    break
            except (urllib.error.URLError, ConnectionError):
                pass
            time.sleep(0.1)
        code, info = _req(f"{base}/api/workspace")
        assert code == 200 and [n["key"] for n in info["notebooks"]] == ["a"] and info["notebooks"][0]["ok"]
        assert _req(f"{base}/results.json?nb=a")[1]["notebook"] == "a"
        assert _req(f"{base}/api/preview?table=t")[1]["rowCount"] == 3
        assert _req(f"{base}/api/preview?table=s")[0] == 400
        assert _req(f"{base}/api/schema", headers={"Host": "evil.example"})[0] == 403          # DNS rebinding
        body = json.dumps({"name": "growth/new-one"}).encode()
        assert _req(f"{base}/api/notebooks", body, {"Content-Type": "text/plain"})[0] == 403    # cross-site form
        assert _req(f"{base}/api/notebooks", body, {"Content-Type": "application/json",
                                                     "Origin": "https://evil.example"})[0] == 403
        code, made = _req(f"{base}/api/notebooks", body, {"Content-Type": "application/json"})
        assert code == 200 and made["key"] == "growth/new-one" and ws.nb("growth/new-one").results_path.exists()
        assert _req(f"{base}/api/notebooks", body, {"Content-Type": "application/json"})[0] == 400   # exists
        bad = json.dumps({"name": "../escape"}).encode()
        assert _req(f"{base}/api/notebooks", bad, {"Content-Type": "application/json"})[0] == 400
        assert not (ws.root / "escape.md").exists()
        js = {"Content-Type": "application/json"}
        code, c = _req(f"{base}/api/comments", json.dumps({"notebook": "a", "block": "s", "text": "why 1?"}).encode(), js)
        assert code == 200 and c["id"] == 1
        assert _req(f"{base}/api/comments", json.dumps({"notebook": "a", "block": "zz", "text": "x"}).encode(), js)[0] == 400
        assert _req(f"{base}/api/comments", json.dumps({"notebook": "a", "block": "s", "text": "x"}).encode(),
                    {"Content-Type": "text/plain"})[0] == 403
        code, r = _req(f"{base}/api/comments/resolve", json.dumps({"id": 1, "note": "fixed"}).encode(), js)
        assert code == 200 and r["status"] == "resolved"
        assert _req(f"{base}/api/comments/resolve", json.dumps({"id": "x"}).encode(), js)[0] == 400
        assert [c["status"] for c in _req(f"{base}/api/comments?nb=a")[1]["comments"]] == ["resolved"]
    finally:
        proc.kill()
        proc.wait()


def test_python_block_with_named_outputs(ws):
    _nb(ws, "m", "```python model\n"
                 "s = t.groupby('k', as_index=False)['v'].sum()\n"
                 "return {'by_k': s, 'total': pd.DataFrame({'n': [int(t['v'].sum())]})}\n```\n"
                 "Total is {{model__total.n | int}}.\n\n"
                 "```sql top\nSELECT k FROM model__by_k ORDER BY v DESC LIMIT 1\n```\n"
                 "```python after\nreturn model__total.assign(m=model__total['n'] * 2)\n```\n"
                 "```chart\n{ type: bar, data: model__by_k, x: k, y: v }\n```\n")
    assert main(["check"]) == 0
    doc = _res(ws, "m")
    assert _blk(doc, "model")["outputs"] == ["model__by_k", "model__total"]
    assert _blk(doc, "model")["rows"] == [["a", 4], ["b", 2]]                      # own name = first output
    assert _blk(doc, "top")["rows"] == [["a"]] and _blk(doc, "after")["rows"] == [[6, 12]]
    assert ">6<" in next(b for b in doc["blocks"] if b["kind"] == "md")["text"]
    assert set(_blk(doc, "top")["deps"]) == {"model"} and "top" in _blk(doc, "model")["usedBy"]


@pytest.mark.parametrize("ret, code", [
    ("{}", "PY_NOT_DATAFRAME"), ("{'bad name': t}", "PY_BAD_OUTPUTS"), ("{'x': 1}", "PY_NOT_DATAFRAME"),
    ("{'clash': t}", "PY_BAD_OUTPUTS"),
])
def test_python_named_output_errors(ws, ret, code):
    _nb(ws, "m", f"```sql model__clash\nSELECT 1 AS x\n```\n```python model\nreturn {ret}\n```\n")
    assert main(["check"]) == 1
    assert code in [d["code"] for d in _res(ws, "m")["diagnostics"]]


def test_reading_a_missing_named_output(ws):
    _nb(ws, "m", "```python model\nreturn {'a': t}\n```\n```python use\nreturn model__nope\n```\n")
    assert main(["check"]) == 1
    d = next(d for d in _res(ws, "m")["diagnostics"] if d["block"] == "use")
    assert d["code"] == "REF_UNKNOWN" and "no output named 'nope'" in d["message"]


def test_comments_flow(ws, capsys):
    from tracebook import comments
    _nb(ws, "growth/a", "# A\n\n```sql s\nSELECT 1 AS x\n```\n")
    assert main(["check"]) == 0
    c = comments.add(ws, "growth/a", "s", "  use distinct orders  ")
    assert c["id"] == 1 and c["line"] == 3 and c["text"] == "use distinct orders" and c["path"] == "notebooks/growth/a.md"
    for nb, blk, text in (("growth/a", "nope", "x"), ("nope", "s", "x"), ("growth/a", "s", " "), ("growth/a", "s", "x" * 5000)):
        with pytest.raises(ProjectError):
            comments.add(ws, nb, blk, text)
    capsys.readouterr()
    assert main(["comments"]) == 0 and "#1 [open] @s (notebooks/growth/a.md:3): use distinct orders" in capsys.readouterr().out
    assert main(["comments", "resolve", "1", "--note", "switched to count(DISTINCT)"]) == 0
    assert main(["comments", "resolve", "1"]) == 2                                  # already resolved
    assert main(["comments", "resolve", "9"]) == 2
    capsys.readouterr()
    assert main(["comments"]) == 0 and "no open comments" in capsys.readouterr().out
    assert comments.items(ws, include_resolved=True)[0]["resolution"] == "switched to count(DISTINCT)"


def test_query_waits_for_a_running_writer(ws, capsys):
    import threading
    _nb(ws, "a", "```sql s\nSELECT 1 AS x\n```\n")
    assert main(["check"]) == 0
    held = threading.Event()

    def writer():                          # what `tracebook check` / the dev server do while running a notebook
        with ws.lock():
            con = ws.connect(schema="nb_a")
            held.set()
            time.sleep(0.5)
            con.close()

    t = threading.Thread(target=writer)
    t.start()
    held.wait()
    capsys.readouterr()
    assert main(["query", "SELECT count(*) AS n FROM t"]) == 0
    assert "3" in capsys.readouterr().out
    t.join()


def test_comment_follows_its_block_and_flags_deleted_ones(ws, capsys):
    from tracebook import comments
    _nb(ws, "a", "```sql s\nSELECT 1 AS x\n```\n")
    assert main(["check"]) == 0
    comments.add(ws, "a", "s", "check this")
    _nb(ws, "a", "# Title\n\nIntro.\n\n```sql s\nSELECT 1 AS x\n```\n")             # block moved down 4 lines
    assert main(["check"]) == 0
    assert comments.items(ws)[0]["line"] == 5 and not comments.items(ws)[0]["orphan"]
    _nb(ws, "a", "# Title\n")                                                      # block deleted
    main(["check"])
    capsys.readouterr()
    assert comments.items(ws)[0]["orphan"]
    assert main(["comments"]) == 0 and "block no longer exists" in capsys.readouterr().out


def test_dev_server_reports_run_crash_only_for_that_notebook(ws):
    _nb(ws, "a", "```sql s\nSELECT 1 AS x\n```\n")
    _nb(ws, "b", "```sql s\nSELECT 2 AS x\n```\n")
    port = _free_port()
    proc = subprocess.Popen([sys.executable, "-m", "tracebook.cli", "dev", "--port", str(port)], cwd=ws.root,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    try:
        def version():
            for _ in range(100):
                try:
                    return _req(f"{base}/version")[1]
                except (urllib.error.URLError, ConnectionError):
                    time.sleep(0.1)
        while version()["version"] < 1:
            time.sleep(0.1)
        (ws.root / "notebooks" / "b.md").write_bytes(b"\xff\xfe not utf-8")         # crashes b's run, not a's
        for _ in range(100):
            v = version()
            if v["errors"]:
                break
            time.sleep(0.1)
        assert list(v["errors"]) == ["b"] and v["error"] is None
        assert "UnicodeDecodeError" in v["errors"]["b"]
        _nb(ws, "b", "```sql s\nSELECT 3 AS x\n```\n")                               # fixed → error cleared
        for _ in range(100):
            v = version()
            if not v["errors"]:
                break
            time.sleep(0.1)
        assert v["errors"] == {}
    finally:
        proc.kill()
        proc.wait()


def test_identical_rerun_gives_identical_results(ws):
    from tracebook.history import summarize
    from tracebook.run import run_notebook
    # parallel GROUP BY returns groups in a different order run to run unless the stored result is ordered
    _nb(ws, "a", "```sql g\nSELECT x % 997 AS k, count(*) AS n FROM range(300000) r(x) GROUP BY 1\n```\n\n"
                 "```sql top\nSELECT k FROM g ORDER BY n DESC, k DESC LIMIT 3\n```\n\n"
                 "```sql flip\nSELECT * FROM g ORDER BY k DESC\n```\n\n"
                 "```sql pick\nSELECT k FROM g LIMIT 2 -- trailing comment\n```\n")
    a, b = run_notebook(ws, "a"), run_notebook(ws, "a")
    assert summarize(a) == summarize(b) and _blk(a, "g")["rows"] == _blk(b, "g")["rows"]
    assert [r[0] for r in _blk(a, "g")["rows"][:3]] == [0, 1, 2]           # unordered → stored sorted by every column
    assert [r[0] for r in _blk(a, "top")["rows"]] == [899, 898, 897]       # the author's ORDER BY is kept
    assert _blk(a, "flip")["rowsHash"] == _blk(a, "g")["rowsHash"]         # same rows, any order → same hash
    assert _blk(a, "pick")["status"] == "ok"
    assert [(d["code"], d["block"]) for d in a["diagnostics"]] == [("UNORDERED_LIMIT", "pick")]


def test_comment_stays_on_its_display_block(ws, capsys):
    from tracebook import comments
    s = "```sql s\nSELECT k, sum(v) AS v FROM t GROUP BY k\n```\n\n"
    chart = lambda title: f'```chart\n{{ type: bar, data: s, x: k, y: v, title: "{title}" }}\n```\n\n'
    _nb(ws, "a", s + chart("Revenue"))
    assert main(["check"]) == 0
    assert comments.add(ws, "a", "chart_1", "label the axis")["anchor"] == "chart Revenue"
    _nb(ws, "a", s + chart("Other") + chart("Revenue"))                     # inserted above: Revenue is now chart_2
    assert main(["check"]) == 0
    c = comments.items(ws)[0]
    assert (c["block"], c["state"]) == ("chart_2", "attached")
    _nb(ws, "a", s.replace("sum(v)", "max(v)") + chart("Other") + chart("Revenue"))   # its numbers changed
    assert main(["check"]) == 0
    assert comments.items(ws)[0]["state"] == "outdated"
    _nb(ws, "a", s + chart("Other"))                                       # gone: orphan, never moved to chart_1
    assert main(["check"]) == 0
    c = comments.items(ws)[0]
    assert c["state"] == "orphan" and c["orphan"]


def test_comment_on_prose_reports_what_changed(ws, capsys):
    from tracebook import comments
    _nb(ws, "b", "```sql n\nSELECT count(*) AS n FROM t\n```\n\nThere are {{n.n}} rows.\n")
    assert main(["check"]) == 0
    md = next(b["id"] for b in _res(ws, "b")["blocks"] if b["kind"] == "md")
    assert comments.add(ws, "b", md, "count orders, not rows")["anchor"] == "md There are {{n.n}} rows."
    _nb(ws, "b", "```sql n\nSELECT count(*) + 1 AS n FROM t\n```\n\nThere are {{n.n}} rows.\n")
    assert main(["check"]) == 0
    capsys.readouterr()
    assert main(["comments"]) == 0
    assert "changed since this comment: was “There are 3 rows.”, now “There are 4 rows.”" in capsys.readouterr().out


def _source_db(path, amounts):
    import duckdb
    path.unlink(missing_ok=True)
    con = duckdb.connect(str(path))
    con.execute("CREATE SCHEMA sales")
    con.execute("CREATE TABLE sales.orders AS SELECT * FROM (VALUES " +
                ", ".join(f"({i}, {a})" for i, a in enumerate(amounts)) + ") v(id, amount)")
    con.close()


def test_source_is_queried_read_only_and_changes_show_in_diff(ws, capsys):
    _source_db(ws.root / "shop.duckdb", [10, 20, 30])
    assert main(["source", "add", "shop", "--type", "duckdb", "--path", "shop.duckdb"]) == 0
    _nb(ws, "a", "```sql spend\nSELECT sum(o.amount) AS total, count(*) AS n FROM shop.sales.orders o\n```\n\n"
                 "```sql both\nSELECT (SELECT sum(v) FROM t) AS local, total FROM spend\n```\n\n"
                 "Spend is {{spend.total}}.\n")
    assert main(["check"]) == 0
    doc = _res(ws, "a")
    assert _blk(doc, "spend")["rows"] == [[60, 3]] and _blk(doc, "spend")["reads"] == ["shop.sales.orders"]
    assert _blk(doc, "both")["rows"] == [[6, 60]]                       # imported table + block, next to a source
    con = ws.connect()
    assert ws.attach_sources(con) == {}
    with pytest.raises(duckdb.Error):                                   # attached READ_ONLY
        con.execute("CREATE TABLE shop.sales.x AS SELECT 1")
    con.close()
    capsys.readouterr()
    assert main(["schema"]) == 0 and "shop.sales.orders" in capsys.readouterr().out
    _source_db(ws.root / "shop.duckdb", [10, 20, 30, 40])               # the database changed; the notebook did not
    assert main(["check"]) == 0
    capsys.readouterr()
    assert main(["--json", "diff"]) == 0
    ch = {c["key"]: c for c in json.loads(capsys.readouterr().out)["changes"]}
    assert "total: 60 → 100" in ch["spend"]["details"] and ch["{{spend.total}}"]["change"] == "~"


def test_unavailable_source_fails_only_its_blocks_and_never_leaks_the_url(ws, monkeypatch, capsys):
    _source_db(ws.root / "s3cr3t.duckdb", [1])
    monkeypatch.setenv("SHOP_URL", str(ws.root / "s3cr3t.duckdb"))
    assert main(["source", "add", "shop", "--type", "duckdb", "--env", "SHOP_URL"]) == 0
    assert "s3cr3t" not in (ws.dir / "sources.json").read_text()
    _nb(ws, "a", "```sql s\nSELECT count(*) AS n FROM shop.sales.orders\n```\n\n```sql d\nSELECT n FROM s\n```\n\n"
                 "```sql ok\nSELECT count(*) AS n FROM t\n```\n")
    assert main(["check"]) == 0
    monkeypatch.setenv("SHOP_URL", str(ws.root / "gone" / "s3cr3t.duckdb"))
    assert main(["check"]) == 1
    doc = _res(ws, "a")
    assert _blk(doc, "s")["status"] == "error" and "SOURCE_UNAVAILABLE" in _blk(doc, "s")["error"]
    assert "$SHOP_URL" in _blk(doc, "s")["error"] and "s3cr3t" not in json.dumps(doc)
    assert _blk(doc, "d")["status"] == "skipped" and _blk(doc, "ok")["status"] == "ok"
    monkeypatch.delenv("SHOP_URL")
    main(["check"])
    assert "SHOP_URL is not set" in _blk(_res(ws, "a"), "s")["error"]
    capsys.readouterr()
    assert main(["source", "add", "x", "--type", "duckdb", "--env", "NOPE_UNSET"]) == 2
    assert main(["source", "add", "main", "--type", "duckdb", "--path", "a.duckdb"]) == 2      # reserved name
    assert main(["source", "add", "pg", "--type", "postgres", "--path", "a.duckdb"]) == 2      # URL must be in env


def test_unknown_catalog_is_still_a_cross_notebook_ref(ws):
    _nb(ws, "a", "```sql s\nSELECT * FROM other.sales.orders\n```\n")
    assert main(["check"]) == 1
    assert [d["code"] for d in _res(ws, "a")["diagnostics"]] == ["CROSS_NOTEBOOK_REF"]


def test_data_browser_lists_and_previews_source_tables(ws, monkeypatch):
    from tracebook import workspace
    _source_db(ws.root / "shop.duckdb", [10, 20])
    assert main(["source", "add", "shop", "--type", "duckdb", "--path", "shop.duckdb"]) == 0
    _nb(ws, "a", "```sql s\nSELECT sum(amount) AS total FROM shop.sales.orders\n```\n")
    assert main(["check"]) == 0
    sch = workspace.schema(ws)
    src = next(t for t in sch["tables"] if t["name"] == "shop.sales.orders")
    assert (src["source"], src["rows"], src["readOnly"]) == ("shop.duckdb", None, True)
    assert [c["name"] for c in src["columns"]] == ["id", "amount"] and src["usedBy"] == [{"notebook": "a", "block": "s"}]
    assert any(t["name"] == "t" for t in sch["tables"]) and sch["sourceErrors"] == {}
    pv = workspace.preview(ws, "shop.sales.orders")
    assert pv["rows"] == [[0, 10], [1, 20]] and pv["rowCount"] is None
    for bad in ("shop.sales", "nope.sales.orders", "shop.sales.missing"):
        with pytest.raises(ProjectError):
            workspace.preview(ws, bad)
    monkeypatch.setenv("GONE_URL", str(ws.root / "s3cr3t" / "x.duckdb"))
    srcs = ws.sources | {"gone": {"type": "duckdb", "env": "GONE_URL"}}
    ws.save_sources(srcs)
    err = workspace.schema(ws)["sourceErrors"]["gone"]
    assert "$GONE_URL" in err and "s3cr3t" not in err
