import Link from "next/link";

export function SiteHeader() {
  return (
    <header className="site-header">
      <Link href="/" className="brand">
        Sentinel
      </Link>
      <nav aria-label="Primary">
        <Link href="/">Status</Link>
        <Link href="/websites">Websites</Link>
      </nav>
    </header>
  );
}
