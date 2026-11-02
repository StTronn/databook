# tracebook docs

Docs + landing site, built with [Geistdocs](https://www.npmjs.com/package/@vercel/geistdocs) (Next.js + Fumadocs). Deployed on Vercel from this folder.

## Edit
- Pages: `content/docs/**/*.mdx`; sidebar order: `meta.json` in each folder.
- Install commands (used by pages and `/agents.md`): `lib/install.ts` only.
- Agent entry point `/agents.md`: the `agent` export in `geistdocs.tsx`.

```bash
cd site
npm install
npm run dev      # http://localhost:3000
npm run build    # what Vercel runs
```

## Publish
Open a PR that changes `site/`: Vercel posts a preview URL on it. Merge to `main`: production updates.

## Agent-readable output
`/agents.md`, `/llms.txt`, `/sitemap.md`, `<page>.md`; `Accept: text/markdown` or a detected AI agent gets Markdown for any page (`proxy.ts`).
