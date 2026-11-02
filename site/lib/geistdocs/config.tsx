import { defineConfig } from "@vercel/geistdocs/config";
import { agent, github, Logo, nav, title } from "@/geistdocs";
import { isSiteUrlConfigured, siteUrl } from "./site-url";

export const config = defineConfig({
  title,
  agent,
  defaultLanguage: "en",
  singleLanguage: true,
  translations: { en: { displayName: "English" } },
  logo: <Logo />,
  github,
  nav,
  siteUrl: isSiteUrlConfigured ? siteUrl.toString() : undefined,
  content: [{ id: "docs", label: "Docs", dir: "content/docs", route: "/" }],
  ai: { enabled: false },
  feedback: { enabled: false },
  webmcp: { enabled: false },
  pageActions: {
    askAI: false,
    openInChat: false,
  },
});
