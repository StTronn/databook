"""`tracebook setup` / `doctor`: copies the skill into detected agents, updates its own copies, never touches yours."""
import json

from tracebook.cli import main
from tracebook import setup


def _home(tmp_path, monkeypatch, *dirs):
    for d in dirs:
        (tmp_path / d).mkdir(parents=True)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(setup.shutil, "which", lambda _: None)        # detection by folders only
    return tmp_path


def test_setup_installs_into_detected_agents_and_shared_dir(tmp_path, monkeypatch, capsys):
    h = _home(tmp_path, monkeypatch, ".claude", ".pi")
    assert main(["--json", "setup"]) == 0
    res = {r["agent"]: r["result"] for r in json.loads(capsys.readouterr().out)}
    assert res == {"Claude Code": "installed", "Codex": "not found, skipped", "pi": "installed",
                   "OpenCode": "not found, skipped", "Agent Skills (shared)": "installed"}
    for d in (".claude/skills", ".pi/agent/skills", ".agents/skills"):
        sk = h / d / "tracebook"
        assert (sk / "SKILL.md").read_text() == (setup.SKILL / "SKILL.md").read_text()
        assert (sk / setup.MARKER).read_text().strip() == setup.tb_version()
    assert not (h / ".codex").exists()


def test_setup_updates_own_copy_and_old_symlink_but_never_a_user_skill(tmp_path, monkeypatch, capsys):
    h = _home(tmp_path, monkeypatch, ".claude", ".pi")
    main(["setup"])
    (h / ".claude/skills/tracebook/SKILL.md").write_text("stale")                     # our copy, outdated
    mine = h / ".pi/agent/skills/tracebook"
    (mine / setup.MARKER).unlink(); (mine / "SKILL.md").write_text("my own skill")    # user-made dir
    shared = h / ".agents/skills/tracebook"
    import shutil; shutil.rmtree(shared); shared.symlink_to(tmp_path)                  # old `skill install` link
    capsys.readouterr()
    assert main(["--json", "setup"]) == 0
    res = {r["agent"]: r["result"] for r in json.loads(capsys.readouterr().out)}
    assert res["Claude Code"] == "updated" and res["Agent Skills (shared)"] == "updated"
    assert res["pi"].startswith("skipped")
    assert (h / ".claude/skills/tracebook/SKILL.md").read_text() != "stale"
    assert (mine / "SKILL.md").read_text() == "my own skill"
    assert not shared.is_symlink() and (shared / "SKILL.md").exists()


def test_setup_named_agent_installs_even_if_not_detected(tmp_path, monkeypatch, capsys):
    h = _home(tmp_path, monkeypatch)
    assert main(["setup", "--agent", "opencode"]) == 0
    assert (h / ".config/opencode/skills/tracebook/SKILL.md").exists()
    assert not (h / ".agents").exists()                                              # only the named one


def test_doctor_and_version(tmp_path, monkeypatch, capsys):
    _home(tmp_path, monkeypatch, ".claude")
    main(["setup"])
    capsys.readouterr()
    assert main(["--json", "doctor"]) == 0
    d = json.loads(capsys.readouterr().out)
    assert d["viewer bundle"] == "ok" and f"skill {setup.tb_version()}" in d["Claude Code"]
    try:
        main(["--version"])
    except SystemExit as e:
        assert e.code == 0
    assert capsys.readouterr().out.strip() == f"tracebook {setup.tb_version()}"
