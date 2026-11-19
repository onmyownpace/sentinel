import { DashboardPanel } from "@/components/DashboardPanel";

export const metadata = {
  title: "Dashboard · Sentinel",
  description: "Health overview, site trends, and recent checks",
};

export default function DashboardPage() {
  return (
    <main className="wide workspace">
      <header className="workspace-hero">
        <p className="workspace-kicker">Monitoring console</p>
        <h1>Dashboard</h1>
        <p>Site health, recent failures, and the next action to take.</p>
      </header>
      <DashboardPanel />
    </main>
  );
}
