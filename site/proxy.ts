import { createProxy } from "@vercel/geistdocs/proxy";
import { config as geistdocsConfig } from "@/lib/geistdocs/config";

// Serves Markdown for `<page>.md`, `Accept: text/markdown` and detected AI agents.
// `/` with `Accept: text/markdown` returns /agents.md. No request tracking.
const proxy = createProxy({
  config: geistdocsConfig,
  additionalMarkdownRoutes: [{ from: "/", to: "/agents.md" }],
  markdownRoutes: [{ from: "/*path", to: "/llms.mdx/*path" }],
});

export const config = {
  matcher: [
    "/((?!api(?:/|$)|_next/static|_next/image|llms\\.mdx|llms\\.txt|agents\\.md|sitemap\\.md|favicon.ico|sitemap.xml|robots.txt|.*\\.(?:png|gif|mp4)$).*)",
  ],
};

export default proxy;
