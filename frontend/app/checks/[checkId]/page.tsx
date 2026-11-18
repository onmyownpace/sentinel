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
    <main className="wide">
      <h1>Check detail</h1>
      <p>
        Full stored observation, on-demand failure analysis when the check failed, and the optional
        viewport screenshot when capture succeeded.
      </p>
      <CheckDetailPanel checkId={checkId} />
    </main>
  );
}
