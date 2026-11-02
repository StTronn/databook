import { DynamicCodeBlock } from "fumadocs-ui/components/dynamic-codeblock";
import { type InstallVariant, installCode } from "@/lib/install";

export function Install({ variant }: { variant?: InstallVariant }) {
  return <DynamicCodeBlock lang="bash" code={installCode(variant)} />;
}
