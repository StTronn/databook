"""`databook setup` / `doctor`: copies the skill into detected agents, updates its own copies, never touches yours."""
import json

from databook.cli import main
from databook import setup


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
                   "pi extension": "installed", "OpenCode": "not found, skipped", "Agent Skills (shared)": "installed"}
    for d in (".claude/skills", ".pi/agent/skills", ".agents/skills"):
        sk = h / d / "databook"
        assert (sk / "SKILL.md").read_text() == (setup.SKILL / "SKILL.md").read_text()
        assert (sk / setup.MARKER).read_text().strip() == setup.tb_version()
    assert not (h / ".codex").exists()


def test_setup_updates_own_copy_and_old_symlink_but_never_a_user_skill(tmp_path, monkeypatch, capsys):
    h = _home(tmp_path, monkeypatch, ".claude", ".pi")
    main(["setup"])
    (h / ".claude/skills/databook/SKILL.md").write_text("stale")                     # our copy, outdated
    mine = h / ".pi/agent/skills/databook"
    (mine / setup.MARKER).unlink(); (mine / "SKILL.md").write_text("my own skill")    # user-made dir
    shared = h / ".agents/skills/databook"
    import shutil; shutil.rmtree(shared); shared.symlink_to(tmp_path)                  # old `skill install` link
    capsys.readouterr()
    assert main(["--json", "setup"]) == 0
    res = {r["agent"]: r["result"] for r in json.loads(capsys.readouterr().out)}
    assert res["Claude Code"] == "updated" and res["Agent Skills (shared)"] == "updated"
    assert res["pi"].startswith("skipped")
    assert (h / ".claude/skills/databook/SKILL.md").read_text() != "stale"
    assert (mine / "SKILL.md").read_text() == "my own skill"
    assert not shared.is_symlink() and (shared / "SKILL.md").exists()


def test_setup_named_agent_installs_even_if_not_detected(tmp_path, monkeypatch, capsys):
    h = _home(tmp_path, monkeypatch)
    assert main(["setup", "--agent", "opencode"]) == 0
    assert (h / ".config/opencode/skills/databook/SKILL.md").exists()
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
    assert capsys.readouterr().out.strip() == f"databook {setup.tb_version()}"


def test_setup_removes_pre_rename_skill_copies_but_not_user_dirs(tmp_path, monkeypatch, capsys):
    h = _home(tmp_path, monkeypatch, ".claude", ".pi")
    old_copy = h / ".claude/skills" / setup.LEGACY[0]
    old_copy.mkdir(parents=True); (old_copy / setup.LEGACY[1]).write_text("0.1.0")
    old_link = h / ".agents/skills" / setup.LEGACY[0]
    old_link.parent.mkdir(parents=True); old_link.symlink_to(tmp_path / "gone")          # dangling repo-path link
    user_dir = h / ".pi/agent/skills" / setup.LEGACY[0]
    user_dir.mkdir(parents=True); (user_dir / "SKILL.md").write_text("mine")              # no marker: user's own
    assert main(["setup"]) == 0
    assert not old_copy.exists() and not old_link.is_symlink()
    assert (user_dir / "SKILL.md").read_text() == "mine"
    assert (h / ".claude/skills/databook/SKILL.md").exists()


def test_pi_extension_installed_updated_never_overwrites_user_file_and_shown_in_doctor(tmp_path, monkeypatch, capsys):
    h = _home(tmp_path, monkeypatch, ".claude")
    ext = h / ".pi/agent/extensions/databook.ts"
    main(["setup"])
    assert not ext.exists()                                                          # pi not detected
    (h / ".pi").mkdir()
    main(["setup"])
    first, rest = ext.read_text().split("\n", 1)
    assert first.startswith(setup.EXT_MARK + setup.tb_version()) and rest == setup.PI_EXT.read_text()
    ext.write_text(setup.EXT_MARK + "0.0.1\nold")                                    # our outdated copy
    capsys.readouterr(); main(["--json", "doctor"])
    assert "outdated" in json.loads(capsys.readouterr().out)["pi extension"]
    main(["--json", "setup"])
    assert {r["agent"]: r["result"] for r in json.loads(capsys.readouterr().out)}["pi extension"] == "updated"
    assert ext.read_text().split("\n", 1)[1] == setup.PI_EXT.read_text()
    main(["--json", "doctor"])
    assert json.loads(capsys.readouterr().out)["pi extension"].startswith(f"extension {setup.tb_version()} — ")
    ext.write_text("// my own bridge\n")                                             # user-made: never touched
    main(["--json", "setup"])
    assert {r["agent"]: r["result"] for r in json.loads(capsys.readouterr().out)}["pi extension"].startswith("skipped")
    assert ext.read_text() == "// my own bridge\n"
    main(["--json", "doctor"])
    assert json.loads(capsys.readouterr().out)["pi extension"].startswith("your own file")
    ext.unlink(); ext.symlink_to(tmp_path / "dev.ts")                                 # dev symlink (dangling): user's
    assert setup.install_ext(ext).startswith("skipped") and ext.is_symlink()
