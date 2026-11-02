import { GeistdocsDocsLayout } from "@vercel/geistdocs/layout";
import type { ReactNode } from "react";
import { config } from "@/lib/geistdocs/config";
import { source } from "@/lib/geistdocs/source";

const Layout = ({ children }: { children: ReactNode }) => (
  <div className="bg-background-200">
    <GeistdocsDocsLayout
      config={config}
      containerProps={{ className: "mx-auto max-w-[1448px] bg-background-200" }}
      tree={source.getPageTree("en")}
    >
      {children}
    </GeistdocsDocsLayout>
  </div>
);

export default Layout;
