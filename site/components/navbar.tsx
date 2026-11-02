import { SearchButton } from "@vercel/geistdocs/controls";
import Link from "next/link";
import { config } from "@/lib/geistdocs/config";

const repo = `https://github.com/${config.github?.owner}/${config.github?.repo}`;

// Own navbar: the package one carries Vercel branding and product menus.
export const Navbar = () => (
  <header className="sticky top-0 z-40 flex h-16 justify-center bg-background-200 shadow-[0_1px_0_0_var(--ds-gray-alpha-400)]">
    <div className="mx-auto flex w-full max-w-[1448px] items-center justify-between px-6">
      <div className="flex items-center gap-6">
        <Link className="flex items-center" href="/">
          {config.logo}
        </Link>
        <nav className="hidden items-center gap-5 text-gray-900 text-sm md:flex">
          {config.nav?.map((item) =>
            "href" in item ? (
              <Link className="transition-colors hover:text-gray-1000" href={item.href} key={item.href}>
                {item.label}
              </Link>
            ) : null
          )}
        </nav>
      </div>
      <div className="flex items-center gap-3">
        <SearchButton className="hidden w-36 md:flex" />
        <a aria-label="GitHub" className="text-gray-900 transition-colors hover:text-gray-1000" href={repo} rel="noopener" target="_blank">
          <svg aria-hidden="true" fill="currentColor" height="18" viewBox="0 0 16 16" width="18">
            <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" />
          </svg>
        </a>
      </div>
    </div>
  </header>
);
