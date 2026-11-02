import "./global.css";
import { geistFontClasses } from "@vercel/geistdocs/core";
import { GeistdocsProvider, GeistdocsThemeScript } from "@vercel/geistdocs/layout";
import { cn } from "@vercel/geistdocs/utils";
import type { Metadata } from "next";
import type { ReactNode } from "react";
import { Navbar } from "@/components/navbar";
import { config } from "@/lib/geistdocs/config";
import { isSiteUrlConfigured, siteUrl } from "@/lib/geistdocs/site-url";

export const metadata: Metadata = {
  metadataBase: isSiteUrlConfigured ? siteUrl : undefined,
  title: { template: "%s · tracebook", default: "tracebook" },
  description:
    "Agent-native data notebook: your coding agent answers data questions in SQL, Python and .xlsx-model blocks on DuckDB, and every number traces to the block that computed it.",
};

const Layout = ({ children }: { children: ReactNode }) => (
  <html className={cn(geistFontClasses, "tailwind tailwind-preflight antialiased")} lang="en" suppressHydrationWarning>
    <head>
      <GeistdocsThemeScript />
    </head>
    <body style={{ backgroundColor: "var(--ds-background-200)" }}>
      <GeistdocsProvider config={config} lang="en">
        <Navbar />
        {children}
      </GeistdocsProvider>
    </body>
  </html>
);

export default Layout;
