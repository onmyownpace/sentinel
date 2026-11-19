import { WebsiteRegistry } from "@/components/WebsiteRegistry";

export const metadata = {
  title: "Websites · Sentinel",
  description: "Register websites for later testing and monitoring",
};

export default function WebsitesPage() {
  return (
    <main className="wide workspace">
      <header className="workspace-hero">
        <p className="workspace-kicker">Monitoring console</p>
        <h1>Websites</h1>
        <p>Register sites, then open Site health for overview, investigate, and automation.</p>
      </header>
      <WebsiteRegistry />
    </main>
  );
}
