"""Viewer ↔ agent bridge (databook.agent, `databook inbox` / `reply`, dev-server endpoints) with a scripted fake agent:
no model calls. The fake agent does what the prompt asks a real one to do: claim, step, edit, check, reply."""
import json
import re
import subprocess
import sys
import time
import urllib.request

import pytest

from databook import agent
from databook.cli import main
from databook.project import Project, ProjectError

from test_workspace import _free_port, _req

NB = "# Sales\n\n```sql s\nSELECT k, sum(v) AS v FROM t GROUP BY k\n```\n\n```chart\n{ type: bar, data: s, x: k, y: v, title: \"Revenue\" }\n```\n\nTotal is {{tot.v}}.\n\n```sql tot\nSELECT sum(v) AS v FROM t\n```\n"


@pytest.fixture
def ws(tmp_path, monkeypatch):
    root = tmp_path / "ws"
    assert main(["init", str(root), "--tz", "UTC"]) == 0
    monkeypatch.chdir(root)
    (root / "notebooks" / "untitled.md").unlink()
    (root / "t.csv").write_text("k,v\na,1\nb,2\na,3\n")
    assert main(["import", "t.csv", "--name", "t"]) == 0
    (root / "notebooks" / "sales.md").write_text(NB)
    assert main(["check"]) == 0
    return Project(root)


def test_request_roundtrip_with_changes_and_undo(ws, capsys):
    r = agent.create(ws, "sales", "use max instead of sum", [{"blockId": "s"}, {"blockId": "chart_1", "quote": "Revenue"}])
    assert r["status"] == "pending" and [c.get("blockId") for c in r["contexts"]] == ["s", "chart_1"]
    capsys.readouterr()
    assert main(["inbox", "--agent", "claude"]) == 0                       # fake agent claims it
    prompt = capsys.readouterr().out
    assert f"Request {r['id']}" in prompt and "use max instead of sum" in prompt
    assert "@Revenue (block chart_1, notebooks/sales.md:" in prompt and 'selected text: "Revenue"' in prompt
    assert f"databook reply {r['id']} --done" in prompt
    assert agent.listener(ws)["state"] == "busy"
    assert main(["reply", r["id"], "--step", "Editing notebooks/sales.md"]) == 0
    nbf = ws.root / "notebooks" / "sales.md"
    nbf.write_text(NB.replace("sum(v) AS v FROM t GROUP BY k", "max(v) AS v FROM t GROUP BY k"))
    capsys.readouterr()
    assert main(["reply", r["id"], "--done", "--text", "Switched @s to max."]) == 0
    assert "change(s)" in capsys.readouterr().out
    done = agent.load(ws, r["id"])
    assert done["status"] == "done" and done["answer"] == "Switched @s to max." and done["check_ok"] is True
    by = {c["blockId"]: c for c in done["changes"]}
    assert by["s"]["detail"].startswith("code edited") and "chart_1" in by          # code + chart data changed
    assert "tot" not in by                                                          # untouched block: no entry
    assert [e["text"] for e in done["events"]] == ["Editing notebooks/sales.md"]
    assert agent.listener(ws)["state"] == "listening"
    agent.undo(ws, r["id"])
    assert nbf.read_text() == NB and agent.load(ws, r["id"])["undone"]
    with pytest.raises(ProjectError, match="already undone"):
        agent.undo(ws, r["id"])


def test_question_without_edits_has_no_changes_and_nothing_to_undo(ws):
    r = agent.create(ws, "sales", "what is the total?", [{"blockId": "tot"}])
    agent.claim(ws, "claude")
    done = agent.finish(ws, r["id"], "The total is 6 (@tot).")
    assert done["status"] == "done" and done["changes"] == [] and done["check_ok"] is None
    with pytest.raises(ProjectError, match="nothing to undo"):
        agent.undo(ws, r["id"])


def test_undo_refuses_after_a_later_manual_edit(ws):
    nbf = ws.root / "notebooks" / "sales.md"
    r = agent.create(ws, "sales", "rename the chart", [])
    agent.claim(ws, "claude")
    nbf.write_text(NB.replace('"Revenue"', '"Sales"'))
    agent.finish(ws, r["id"], "Renamed.")
    nbf.write_text(nbf.read_text() + "\nMy own note.\n")                            # user edits afterwards
    with pytest.raises(ProjectError, match="changed after the agent"):
        agent.undo(ws, r["id"])
    assert "My own note." in nbf.read_text()


def test_stop_makes_further_replies_fail_and_claim_is_fifo(ws, capsys):
    a = agent.create(ws, "sales", "first", [])
    time.sleep(0.002)
    b = agent.create(ws, "sales", "second", [])
    assert agent.claim(ws, "claude")["id"] == a["id"]
    agent.stop(ws, a["id"])
    assert main(["reply", a["id"], "--step", "still going"]) == 2
    assert "stopped by the user" in capsys.readouterr().err
    assert agent.claim(ws, "claude")["id"] == b["id"]
    assert agent.claim(ws, "claude") is None
    assert main(["inbox"]) == 1                                                     # nothing pending


def test_listener_states(ws, monkeypatch):
    assert agent.listener(ws)["state"] == "offline"
    agent.beat(ws, "claude")
    assert agent.listener(ws)["state"] == "listening"
    real = time.time
    monkeypatch.setattr(agent.time, "time", lambda: real() + agent.LISTEN_FRESH_S + 1)
    assert agent.listener(ws)["state"] == "offline"                                 # stale blocking listener


def test_inbox_wait_times_out_and_bad_ids_are_refused(ws):
    t = time.time()
    assert main(["inbox", "--wait", "--timeout", "1.2"]) == 1 and time.time() - t >= 1
    with pytest.raises(ProjectError, match="bad request id"):
        agent.load(ws, "../../etc")


def test_dev_server_agent_endpoints_require_page_token(ws):
    port = _free_port()
    proc = subprocess.Popen([sys.executable, "-m", "databook.cli", "dev", "--port", str(port)], cwd=ws.root,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    js = {"Content-Type": "application/json"}
    try:
        for _ in range(100):
            try:
                html = urllib.request.urlopen(base + "/", timeout=5).read().decode()
                break
            except OSError:
                time.sleep(0.1)
        token = re.search(r"window\.__TB_TOKEN__=\"([^\"]+)\"", html)[1]
        assert html.index("__TB_TOKEN__") < html.index("<script", html.index("__TB_TOKEN__"))   # injected before the bundle
        body = json.dumps({"notebook": "sales", "text": "why?", "contexts": [{"blockId": "tot"}]}).encode()
        assert _req(base + "/api/agent/requests", body, js)[0] == 403                     # no token
        assert _req(base + "/api/agent/requests", body, {**js, "X-Databook-Token": "nope"})[0] == 403
        code, r = _req(base + "/api/agent/requests", body, {**js, "X-Databook-Token": token})
        assert code == 200 and r["id"]
        code, th = _req(base + "/api/agent/thread?nb=sales")
        assert code == 200 and th["listener"]["state"] == "offline" and th["requests"][0]["text"] == "why?"
        assert "before" not in th["requests"][0]
        stop = json.dumps({"id": r["id"]}).encode()
        assert _req(base + "/api/agent/stop", stop, {**js, "X-Databook-Token": token}) == (200, {"status": "stopped"})
    finally:
        proc.terminate()
        proc.wait(5)
