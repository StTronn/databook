/**
 * databook ↔ pi bridge (installed by `databook setup` into <pi agent dir>/extensions/).
 * In a databook workspace (a `.databook/` dir at or above cwd), interactive sessions only: heartbeats the listener
 * (`databook inbox --beat`), watches .databook/agent/requests/ (fs.watch + 3 s poll), claims ONE pending request at a
 * time (`databook inbox`) and sends its prompt as a user message (followUp when pi is busy). The next request is
 * claimed after the agent settles. Nothing here calls a model.
 */
import { execFile } from "node:child_process";
import * as fs from "node:fs";
import * as path from "node:path";
import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";

export default function (pi: ExtensionAPI) {
	let ctx: ExtensionContext | undefined, root = "", session: string | undefined;
	let timers: NodeJS.Timeout[] = [], watcher: fs.FSWatcher | undefined;
	let inflight = 0, running = false, dead = false; // inflight: time our last request was sent (0 = none)

	const db = (args: string[]) => new Promise<{ code: number; out: string }>((resolve) =>
		execFile("databook", [...args, "--agent", "pi", ...(session ? ["--session", session] : [])], { cwd: root, timeout: 60_000 },
			(err: any, out) => {
				if (err?.code === "ENOENT" && !dead) {
					dead = true;
					ctx?.ui.notify("databook: `databook` is not on PATH; viewer requests will not reach this session", "warning");
				}
				resolve({ code: err ? (typeof err.code === "number" ? err.code : -1) : 0, out: String(out ?? "") });
			}));

	const pending = () => {
		try {
			const d = path.join(root, ".databook/agent/requests");
			return fs.readdirSync(d).some((f) => f.endsWith(".json") && !f.startsWith(".") &&
				(() => { try { return JSON.parse(fs.readFileSync(path.join(d, f), "utf8")).status === "pending"; } catch { return false; } })());
		} catch { return false; }
	};

	const check = async () => {
		if (!ctx || dead || running) return;
		if (inflight && ctx.isIdle() && Date.now() - inflight > 10_000) inflight = 0; // settled without our event
		if (inflight || !pending()) return;
		running = true;
		try {
			const r = await db(["inbox"]);
			if (r.code === 0 && r.out.trim() && ctx) {
				inflight = Date.now();
				pi.sendUserMessage(r.out.replace(/^Then run `databook inbox --wait`.*$/m, "").trim(), { deliverAs: "followUp" });
			}
		} finally { running = false; }
	};

	const stop = () => { timers.forEach(clearInterval); timers = []; watcher?.close(); watcher = undefined; ctx = undefined; };

	pi.on("session_start", async (_e, c) => {
		stop();
		if (!c.hasUI) return; // print/json mode: one-shot runs must not steal viewer requests
		let d = path.resolve(c.cwd);
		while (!fs.existsSync(path.join(d, ".databook")) || !fs.statSync(path.join(d, ".databook")).isDirectory()) {
			if (path.dirname(d) === d) return; // not in a databook workspace
			d = path.dirname(d);
		}
		ctx = c; root = d; dead = false; inflight = 0;
		try { session = c.sessionManager.getSessionId(); } catch { session = undefined; }
		const beat = () => { if (!inflight && !dead) db(["inbox", "--beat"]); };
		beat();
		timers.push(setInterval(beat, 20_000), setInterval(() => {
			if (!watcher) try {
				watcher = fs.watch(path.join(root, ".databook/agent/requests"), () => void check())
					.on("error", () => { watcher?.close(); watcher = undefined; }); // dir removed: re-attach on next poll
			} catch {}
			void check();
		}, 3_000));
		void check();
	});
	pi.on("agent_settled", async () => { inflight = 0; void check(); });
	pi.on("session_shutdown", async () => stop());
}
