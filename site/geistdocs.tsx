import type { GeistdocsAgentReadinessConfig } from "@vercel/geistdocs/config";
import { DOCTOR, INSTALL_CLI, NPX_CLI, SETUP } from "@/lib/install";

export const Logo = () => (
  <span className="font-medium font-mono text-gray-1000 text-lg leading-none tracking-[-3%]">
    tracebook
  </span>
);

export const github = {
  owner: "StTronn",
  repo: "tracebook",
  branch: "main",
  editPath: "site/content/docs/{path}",
};

export const nav = [
  { label: "Docs", href: "/installation" },
  { label: "CLI", href: "/cli" },
  { label: "Examples", href: "/examples" },
];

export const title = "tracebook";

export const agent = {
  product: {
    name: "tracebook",
    description:
      "Agent-native data notebook CLI. A coding agent answers data questions in a markdown notebook of SQL, Python and .xlsx-model blocks run on DuckDB; every number in the prose is a {{block.col}} reference to the block that computed it.",
    category: "Data analysis",
    audience: ["Coding agents", "Analysts and engineers working with data files or databases"],
    useCases: [
      "Answer a data question from CSV, Excel, JSON, SQLite, Parquet files or a read-only database",
      "Build a checked, reviewable notebook or report instead of a one-off script",
      "Rerun an analysis on a new data export and list which numbers changed",
      "Export a self-contained HTML report or one block's result as CSV",
    ],
  },
  instructions: [
    `Install: \`${INSTALL_CLI}\` (or \`${NPX_CLI} <cmd>\` without installing), then \`${SETUP}\` to add the skill to every detected agent; \`${DOCTOR}\` shows what is wired. Details: /installation.md.`,
    "The skill's SKILL.md is the workflow to follow; `tracebook --help` lists commands.",
    "Workflow: `tracebook comments` → `init` → `import` → `schema`/`query` → edit `notebooks/<name>.md` → `tracebook check` until `✓ … 0 error(s)` → `export`.",
    "Never type a computed number into prose; reference it as `{{block.col | fmt}}` from a block that returns one row.",
    "Read /concepts/blocks.md for block syntax and /cli.md for every command.",
  ],
  links: [
    {
      label: "Agent skill (SKILL.md)",
      href: "https://github.com/StTronn/tracebook/blob/main/src/tracebook/skill/SKILL.md",
      description: "The workflow the agent follows",
    },
  ],
} satisfies GeistdocsAgentReadinessConfig;
