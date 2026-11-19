import { WebsiteRegistry } from "@/components/WebsiteRegistry";

export const metadata = {
  title: "Websites · Sentinel",
  description: "Register websites for later testing and monitoring",
};

export default function WebsitesPage() {
  return (
    <main className="wide workspace">
      <header className="workspace-hero">
        <p className="workspace-kicker">Workspace</p>
        <h1>Websites</h1>
        <p>Manage monitored sites and open their check history.</p>
      </header>
      <WebsiteRegistry />
    </main>
  );
}
