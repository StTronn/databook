// Single source of truth for install commands (pages, /agents.md). Change them here only.

export const NPM_PACKAGE = "tracebook-cli";
export const INSTALL_CLI = `npm i -g ${NPM_PACKAGE}`;
export const NPX_CLI = `npx ${NPM_PACKAGE}`;
export const SETUP = "tracebook setup";
export const DOCTOR = "tracebook doctor";
export const UPGRADE_CLI = `npm i -g ${NPM_PACKAGE}@latest`;

// Code shown by <Install variant=…/> in pages and in their Markdown export.
export const INSTALL_BLOCKS = {
  default: [
    `${INSTALL_CLI}   # CLI (installs uv + Python on first run if missing)`,
    `${SETUP}         # add the skill to every agent found`,
    "",
    "# or without installing",
    `${NPX_CLI} --help`,
  ],
  setup: [`${SETUP}    # copy the skill into each detected agent`, `${DOCTOR}   # show what is wired`],
  upgrade: [UPGRADE_CLI, SETUP],
};

export type InstallVariant = keyof typeof INSTALL_BLOCKS;

export const installCode = (variant: InstallVariant = "default") => INSTALL_BLOCKS[variant].join("\n");
