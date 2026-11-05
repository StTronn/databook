"""agent.deliver(): viewer requests pushed to an open Codex session via `codex queue` (fake `codex` on PATH, no model)."""
import json
import os
import sys

import pytest

from databook import agent

from test_agent import ws  # noqa: F401  (fixture)

FAKE = """#!{py}
import json, os, sys
with open(os.environ["FAKE_CODEX_LOG"], "a") as f:
    f.write(json.dumps(sys.argv[1:]) + "\\n")
if os.environ.get("FAKE_CODEX_FAIL"):
    sys.stderr.write("Error: failed to queue session message: no rollout found\\n")
    sys.exit(1)
print("Queued message x for thread y.")
"""


@pytest.fixture
def codex(tmp_path, monkeypatch):
    bindir, log = tmp_path / "bin", tmp_path / "codex.log"
    bindir.mkdir()
    exe = bindir / "codex"
    exe.write_text(FAKE.format(py=sys.executable))
    exe.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_CODEX_LOG", str(log))
    return lambda: [json.loads(l) for l in log.read_text().splitlines()] if log.exists() else []


def test_codex_listener_gets_request_queued_and_claimed(ws, codex):
    agent.beat(ws, "codex", "thread-123")
    r = agent.create(ws, "sales", "what is the total?", [{"blockId": "tot"}])
    (argv,) = codex()
    assert argv[:4] == ["queue", "--thread", "thread-123", "--message"] and len(argv) == 5
    assert argv[4] == agent.prompt(agent.load(ws, r["id"])).rsplit("\n", 1)[0]       # prompt minus the inbox --wait hint
    assert f"Request {r['id']}" in argv[4] and "inbox --wait" not in argv[4]
    got = agent.load(ws, r["id"])
    assert got["status"] == "claimed" and got["agent"] == "codex" and got["events"] == []
    lst = agent.listener(ws)
    assert (lst["state"], lst["session"], lst["request"]) == ("busy", "thread-123", r["id"])
    r2 = agent.create(ws, "sales", "and the max?", [])                              # busy session: still queued
    assert [a[2] for a in codex()] == ["thread-123", "thread-123"] and agent.load(ws, r2["id"])["status"] == "claimed"
    agent.finish(ws, r["id"], "6")
    agent.finish(ws, r2["id"], "3")
    assert agent.listener(ws)["state"] == "listening"


def test_backlog_is_pushed_oldest_first(ws, codex):
    old = agent.create(ws, "sales", "older", [])                                    # nobody listening yet
    assert codex() == [] and agent.load(ws, old["id"])["status"] == "pending"
    agent.beat(ws, "codex", "t1")
    new = agent.create(ws, "sales", "newer", [])
    assert [f"Request {x['id']}" in a[4] for a, x in zip(codex(), (old, new))] == [True, True]
    assert {agent.load(ws, x["id"])["status"] for x in (old, new)} == {"claimed"}


@pytest.mark.parametrize("who", [None, ("claude", None), ("codex", None), ("pi", "s1")])
def test_no_codex_listener_no_push(ws, codex, who):
    if who:
        agent.beat(ws, *who)
    r = agent.create(ws, "sales", "hi", [])
    assert codex() == [] and agent.load(ws, r["id"])["status"] == "pending"


def test_stale_codex_listener_no_push(ws, codex, monkeypatch):
    agent.beat(ws, "codex", "t1")
    real = agent.time.time
    monkeypatch.setattr(agent.time, "time", lambda: real() + agent.BUSY_FRESH_S + 1)
    r = agent.create(ws, "sales", "hi", [])
    assert codex() == [] and agent.load(ws, r["id"])["status"] == "pending"


def test_queue_failure_is_recorded_and_request_stays_pullable(ws, codex, monkeypatch):
    monkeypatch.setenv("FAKE_CODEX_FAIL", "1")
    agent.beat(ws, "codex", "gone")
    r = agent.create(ws, "sales", "hi", [])                                          # must not raise
    assert len(codex()) == 1
    got = agent.load(ws, r["id"])
    assert got["status"] == "pending" and "no rollout found" in got["events"][0]["text"]
    assert agent.listener(ws)["state"] == "offline"                                  # unreachable → no further pushes
    agent.create(ws, "sales", "again", [])
    assert len(codex()) == 1
    assert agent.claim(ws, "codex", "gone")["id"] == r["id"]                         # `databook inbox` still gets it


def test_codex_missing_from_path(ws, monkeypatch, tmp_path):
    monkeypatch.setenv("PATH", str(tmp_path))                                        # no codex anywhere
    agent.beat(ws, "codex", "t1")
    r = agent.create(ws, "sales", "hi", [])
    got = agent.load(ws, r["id"])
    assert got["status"] == "pending" and "FileNotFoundError" in got["events"][0]["text"]
