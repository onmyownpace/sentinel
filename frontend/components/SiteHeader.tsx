import Link from "next/link";

import { AuthNav } from "@/components/AuthNav";

export function SiteHeader() {
  return (
    <header className="site-header">
      <Link href="/" className="brand">
        Sentinel
      </Link>
      <nav aria-label="Primary">
        <Link href="/">Status</Link>
        <Link href="/dashboard">Dashboard</Link>
        <Link href="/websites">Websites</Link>
        <AuthNav />
      </nav>
    </header>
  );
}
