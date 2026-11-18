import { WebsiteRegistry } from "@/components/WebsiteRegistry";

export const metadata = {
  title: "Websites · Sentinel",
  description: "Register websites for later testing and monitoring",
};

export default function WebsitesPage() {
  return (
    <main className="wide">
      <h1>Websites</h1>
      <p>
        Register a site by name and base URL, then run a browser check when you are allowed to test
        it. Sites belong to your signed-in account. Open <strong>health & trends</strong> for
        drill-down charts and check detail.
      </p>
      <p className="hint">
        Failed-check drafts can be delivered by n8n when you set a free webhook
        URL in the workflow. Delivery stays off while that URL is empty.
      </p>
      <WebsiteRegistry />
    </main>
  );
}
