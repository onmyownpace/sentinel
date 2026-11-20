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
    <main className="wide workspace">
      <header className="workspace-hero">
        <p className="workspace-kicker">Site health</p>
        <h1>Monitoring console</h1>
        <p>Overview for trends, Investigate for failures, Automation for journeys and scheduling.</p>
      </header>
      <SiteHealthPanel websiteId={websiteId} />
    </main>
  );
}
