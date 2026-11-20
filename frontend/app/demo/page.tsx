import { DemoExperience } from "@/components/DemoExperience";

export const metadata = {
  title: "Demo · Sentinel",
  description: "Try a failed check and AI analysis with no account",
};

export default function DemoPage() {
  return (
    <main className="wide workspace demo-page">
      <header className="workspace-hero demo-hero">
        <p className="workspace-kicker">Portfolio demo · no login</p>
        <h1>A failed check, explained</h1>
        <p>
          Sample monitoring data from the seeded demo site. Open the failure, run analysis, and
          see what Sentinel surfaces — no account required.
        </p>
      </header>
      <DemoExperience />
    </main>
  );
}
