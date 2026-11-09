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
        Register a site by name and base URL, then run a browser check when you
        are allowed to test it. This is one shared list for the development
        process. There are no accounts.
      </p>
      <WebsiteRegistry />
    </main>
  );
}
