import { SiteHealthPanel } from "@/components/SiteHealthPanel";

type SitePageProps = {
  params: Promise<{ websiteId: string }>;
};

export async function generateMetadata({ params }: SitePageProps) {
  const { websiteId } = await params;
  return {
    title: "Site health · Sentinel",
    description: `Health and trends for website ${websiteId}`,
  };
}

export default async function SiteHealthPage({ params }: SitePageProps) {
  const { websiteId } = await params;
  return (
    <main className="wide">
      <h1>Site health</h1>
      <p>
        Per-site uptime, latency trends, monitoring state, and check history. Charts are local SVG
        from MON-1 samples — not a paid analytics product.
      </p>
      <SiteHealthPanel websiteId={websiteId} />
    </main>
  );
}
