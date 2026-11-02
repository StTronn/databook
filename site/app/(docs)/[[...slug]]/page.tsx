import { MobileDocsBar } from "@vercel/geistdocs/mobile-docs-bar";
import { createDocsPage } from "@vercel/geistdocs/pages/docs";
import { getMDXComponents } from "@/components/geistdocs/mdx-components";
import { config } from "@/lib/geistdocs/config";
import { geistdocsSource } from "@/lib/geistdocs/source";

const docsPage = createDocsPage({
  config,
  mdx: ({ link }) => getMDXComponents({ a: link }),
  source: geistdocsSource,
  tableOfContentPopover: { enabled: false },
  renderTop: ({ data }) => <MobileDocsBar toc={data.toc} />,
});

export default docsPage.Page;
export const generateStaticParams = docsPage.generateStaticParams;
export const generateMetadata: typeof docsPage.generateMetadata = async (props) => {
  const metadata = await docsPage.generateMetadata(props);
  const { slug } = await props.params;
  return slug?.length ? metadata : { ...metadata, title: { absolute: "tracebook" } };
};
