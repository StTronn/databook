import { createMdxComponents } from "@vercel/geistdocs/mdx";
import type { MDXComponents } from "mdx/types";
import { Install } from "@/components/install";

export const getMDXComponents = (components?: MDXComponents): MDXComponents =>
  createMdxComponents({ Install, ...components });
