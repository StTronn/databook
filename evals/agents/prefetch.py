"""Host-side runtimes that job configs bind-mount read-only into trials (environment.mounts, ${EVALS_RT} = this
cache, exported by evals/run.sh). Harbor's built-in claude-code agent finds the mounted binary at the pinned
`version` and skips its own install, so trials download and upload nothing.

evals/.cache/runtime/
  claude-<version>-linux-<arch>   Claude Code native Linux binary, sha256-checked against the release manifest (cache)
  claude                          hard link to the build for the config's version + Docker arch → /usr/local/bin/claude
  databook/                      only if a mount uses it: databook + deps (pinned by uv.lock) for the task image's
                                  python, `uv pip install --target` → /opt/databook (rebuilt every run: local code)
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "evals/.cache/runtime"
CLAUDE_BASE = "https://downloads.claude.ai/claude-code-releases"
TASK_PYTHON = "3.12"            # python3 of the task image (ubuntu-24-04); a mismatch fails at `databook --help`


def docker_arch() -> str:
    a = subprocess.run(["docker", "info", "--format", "{{.Architecture}}"], capture_output=True, text=True,
                       check=True).stdout.strip()
    return {"aarch64": "arm64", "arm64": "arm64", "x86_64": "x64", "amd64": "x64"}[a]


def claude(version: str, arch: str) -> None:
    out = CACHE / f"claude-{version}-linux-{arch}"
    if not out.is_file():
        meta = json.load(urllib.request.urlopen(f"{CLAUDE_BASE}/{version}/manifest.json"))["platforms"][f"linux-{arch}"]
        tmp = out.with_suffix(".part")
        print(f"prefetch: Claude Code {version} linux-{arch} ({meta.get('size', '?')} bytes)", file=sys.stderr)
        with urllib.request.urlopen(f"{CLAUDE_BASE}/{version}/linux-{arch}/claude") as r, open(tmp, "wb") as f:
            shutil.copyfileobj(r, f)
        if hashlib.sha256(tmp.read_bytes()).hexdigest() != meta["checksum"]:
            tmp.unlink()
            raise SystemExit(f"prefetch: checksum mismatch for Claude Code {version} linux-{arch}")
        tmp.rename(out)
    out.chmod(0o755)
    link = CACHE / "claude"
    link.unlink(missing_ok=True)
    os.link(out, link)  # hard link, not symlink: Docker Desktop bind mounts don't follow host symlinks reliably


def databook(arch: str) -> None:
    out, whl = CACHE / "databook", CACHE / "wheel"
    for d in (out, whl):
        shutil.rmtree(d, ignore_errors=True)
    run = lambda *a, **kw: subprocess.run(a, cwd=ROOT, check=True, **kw)
    run("uv", "build", "-q", "--wheel", "-o", str(whl))
    cons = whl / "c.txt"
    cons.write_text(run("uv", "export", "-q", "--frozen", "--no-dev", "--no-emit-project", "--no-hashes",
                        capture_output=True, text=True).stdout)
    m = "aarch64" if arch == "arm64" else "x86_64"
    run("uv", "pip", "install", "-q", "--target", str(out), "--python-platform", f"{m}-manylinux_2_28",
        "--python-version", TASK_PYTHON, "--only-binary", ":all:", "-c", str(cons), *map(str, whl.glob("*.whl")))
    shutil.rmtree(whl)


def main(config: str) -> None:
    cfg = yaml.safe_load(Path(config).read_text())
    agents = [a for a in cfg.get("agents", []) if a.get("name") == "claude-code"]
    versions = {str((a.get("kwargs") or {}).get("version") or "") for a in agents}
    if not agents:
        return
    if len(versions) != 1 or "" in versions:
        raise SystemExit(f"prefetch: {config}: claude-code agents need one pinned kwargs.version, got {versions}")
    CACHE.mkdir(parents=True, exist_ok=True)
    arch = docker_arch()
    claude(versions.pop(), arch)
    if any("/databook" in m.get("source", "") for m in (cfg.get("environment") or {}).get("mounts") or []):
        databook(arch)


if __name__ == "__main__":
    main(sys.argv[1])
