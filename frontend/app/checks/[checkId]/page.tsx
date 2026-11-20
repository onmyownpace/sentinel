import { CheckDetailPanel } from "@/components/CheckDetailPanel";

type CheckPageProps = {
  params: Promise<{ checkId: string }>;
};

export async function generateMetadata({ params }: CheckPageProps) {
  const { checkId } = await params;
  return {
    title: "Check detail · Sentinel",
    description: `Stored check ${checkId}`,
  };
}

export default async function CheckDetailPage({ params }: CheckPageProps) {
  const { checkId } = await params;
  return (
    <main className="wide workspace">
      <header className="workspace-hero">
        <p className="workspace-kicker">Check detail</p>
        <h1>Observation</h1>
        <p>Stored check result, failure analysis when needed, and screenshot when captured.</p>
      </header>
      <CheckDetailPanel checkId={checkId} />
    </main>
  );
}
