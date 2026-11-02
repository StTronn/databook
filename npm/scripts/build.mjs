// prepack: build the tracebook wheel from the repo root into dist/ and pin its dependencies (uv.lock → constraints).
// Fails when package.json and pyproject.toml disagree on the version, so npm and the wheel always match.
import { execFileSync } from "node:child_process";
import { mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(dirname(fileURLToPath(import.meta.url)));   // npm/
const root = dirname(here);
const pkg = JSON.parse(readFileSync(join(here, "package.json"), "utf8")).version;
const py = readFileSync(join(root, "pyproject.toml"), "utf8").match(/^version\s*=\s*"([^"]+)"/m)?.[1];
if (pkg !== py) throw new Error(`version mismatch: npm/package.json ${pkg} vs pyproject.toml ${py}`);
const dist = join(here, "dist");
rmSync(dist, { recursive: true, force: true });
mkdirSync(dist);
execFileSync("uv", ["build", "--wheel", "-q", "-o", dist], { cwd: root, stdio: "inherit" });
const cons = execFileSync("uv", ["export", "-q", "--frozen", "--no-dev", "--no-emit-project", "--no-hashes"], { cwd: root });
writeFileSync(join(dist, "constraints.txt"), cons);
rmSync(join(dist, ".gitignore"), { force: true });   // uv writes `*` here; npm would then drop the wheel
console.log(`built tracebook ${py} wheel + constraints into npm/dist`);
