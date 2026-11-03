# databook-cli

Agent-native data notebook. Your coding agent (Claude Code, Codex, pi, OpenCode, …) answers data questions inside a notebook of SQL / Python / `.xlsx`-model blocks on DuckDB; every number traces back to the block that computed it.

```bash
npm i -g databook-cli      # or run without installing: npx databook-cli <command>
databook setup             # puts the agent skill into every coding agent it finds
databook init analysis     # then put your files in analysis/data/ and ask your agent
```

The first run installs [uv](https://docs.astral.sh/uv/) if it is missing (uv provides Python). `databook doctor` shows versions and where the skill is installed. Source, docs and examples: https://github.com/StTronn/databook
