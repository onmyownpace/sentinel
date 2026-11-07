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
        Register a site by name and base URL. This is one shared list for the
        development process. There are no accounts, and Sentinel does not open
        the site yet.
      </p>
      <WebsiteRegistry />
    </main>
  );
}
