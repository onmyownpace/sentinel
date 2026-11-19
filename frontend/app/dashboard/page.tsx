import { DashboardPanel } from "@/components/DashboardPanel";

export const metadata = {
  title: "Dashboard · Sentinel",
  description: "Health overview, site trends, and recent checks",
};

export default function DashboardPage() {
  return (
    <main className="wide workspace">
      <header className="workspace-hero">
        <p className="workspace-kicker">Workspace</p>
        <h1>Monitoring overview</h1>
        <p>Review site health, response times, and recent failures.</p>
      </header>
      <DashboardPanel />
    </main>
  );
}
