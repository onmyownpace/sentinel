import { DashboardPanel } from "@/components/DashboardPanel";

export const metadata = {
  title: "Dashboard · Sentinel",
  description: "Health overview, site trends, and recent checks",
};

export default function DashboardPage() {
  return (
    <main className="wide">
      <h1>Dashboard</h1>
      <p>
        Account health overview with MON-1 uptime and latency, links into per-site drill-down, and
        recent checks. Sign in is required.
      </p>
      <DashboardPanel />
    </main>
  );
}
