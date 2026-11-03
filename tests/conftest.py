import json
import shutil
from pathlib import Path

import pytest

from databook.cli import main
from databook.project import Project

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture
def project(tmp_path, monkeypatch):
    """Empty project (tz Asia/Kolkata); cwd set to it so CLI commands resolve it."""
    root = tmp_path / "p"
    assert main(["init", str(root), "--tz", "Asia/Kolkata"]) == 0
    monkeypatch.chdir(root)
    return Project(root)


@pytest.fixture(scope="session")
def demo_root(tmp_path_factory):
    root = tmp_path_factory.mktemp("demo") / "d"
    assert main(["init", str(root), "--template", "razorpay-funnel", "--demo"]) == 0
    return root


@pytest.fixture
def demo(demo_root, tmp_path, monkeypatch):
    """Fresh copy of the demo project with data imported."""
    root = tmp_path / "demo"
    shutil.copytree(demo_root, root)
    monkeypatch.chdir(root)
    assert main(["import", *map(str, sorted((root / "data").glob("*.xlsx")))]) == 0
    return Project(root)


def results(p: Project) -> dict:
    return json.loads(p.results_path.read_text())


def block(doc: dict, bid: str) -> dict:
    return next(b for b in doc["blocks"] if b["id"] == bid)


def row(doc: dict, bid: str) -> dict:
    b = block(doc, bid)
    assert b["status"] == "ok", b.get("error")
    return dict(zip([c["name"] for c in b["columns"]], b["rows"][0]))
