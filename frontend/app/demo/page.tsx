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
        <h1>Test a site, or try the sample</h1>
        <p>
          Run a lightweight HTTP check on any public URL, or open the seeded failure and analysis —
          no account required.
        </p>
      </header>
      <DemoExperience />
    </main>
  );
}
