import { createSource } from "@vercel/geistdocs/source";
import { docs } from "@/.source/server";
import { type InstallVariant, installCode } from "@/lib/install";
import { config } from "./config";

export const geistdocsSource = createSource({
  docs,
  config,
  baseUrl: "/",
  markdown: {
    components: {
      Install: ({ props }) => `\`\`\`bash\n${installCode(props.variant as InstallVariant | undefined)}\n\`\`\``,
    },
  },
});

export const source = geistdocsSource.source;
