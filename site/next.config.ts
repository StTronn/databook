import { createGeistdocs } from "@vercel/geistdocs/next";
import type { NextConfig } from "next";

const withGeistdocs = createGeistdocs();

const config: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
};

export default withGeistdocs(config);
