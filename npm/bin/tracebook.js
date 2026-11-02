#!/usr/bin/env node
// tracebook npm launcher: runs the bundled Python wheel through uv (`uv tool run`, cached after the first call).
// uv brings its own Python, so the only prerequisite is uv itself, installed here on first use if missing.
"use strict";
const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const dist = path.join(__dirname, "..", "dist");
const wheel = fs.readdirSync(dist).find((f) => f.endsWith(".whl"));
if (!wheel) { console.error("tracebook: package is missing its wheel (dist/*.whl); reinstall tracebook-cli"); process.exit(1); }

function findUv() {
  const exe = process.platform === "win32" ? "uv.exe" : "uv";
  const dirs = [process.env.UV_INSTALL_DIR, ...(process.env.PATH || "").split(path.delimiter),
    path.join(os.homedir(), ".local", "bin"), path.join(os.homedir(), ".cargo", "bin")].filter(Boolean);
  if (process.env.TRACEBOOK_UV) return process.env.TRACEBOOK_UV;
  for (const d of dirs) { const p = path.join(d, exe); if (fs.existsSync(p)) return p; }
  return null;
}

let uv = findUv();
if (!uv) {
  if (process.platform === "win32") {
    console.error('tracebook needs uv: powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"');
    process.exit(1);
  }
  console.error("tracebook: first run, installing uv (Python toolchain) from https://astral.sh/uv …");
  const r = spawnSync("sh", ["-c", "curl -LsSf https://astral.sh/uv/install.sh | sh"], { stdio: ["ignore", "ignore", "inherit"] });
  uv = r.status === 0 ? findUv() : null;
  if (!uv) { console.error("tracebook: could not install uv; install it from https://docs.astral.sh/uv/ and retry"); process.exit(1); }
}

const args = ["tool", "run", "--quiet", "--from", path.join(dist, wheel)];
const cons = path.join(dist, "constraints.txt");
if (fs.existsSync(cons)) args.push("--constraints", cons);   // dependency versions pinned to the repo's uv.lock
const r = spawnSync(uv, [...args, "tracebook", ...process.argv.slice(2)], { stdio: "inherit" });
if (r.error) { console.error(`tracebook: ${r.error.message}`); process.exit(1); }
process.exit(r.status === null ? 1 : r.status);
