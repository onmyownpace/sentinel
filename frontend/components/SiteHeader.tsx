"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { AuthNav } from "@/components/AuthNav";

export function SiteHeader() {
  const pathname = usePathname();

  return (
    <header className="site-header">
      <Link href="/" className="brand">
        Sentinel
      </Link>
      <nav aria-label="Primary">
        <Link href="/" className={navClass(pathname, "/", true)}>
          Explore demo
        </Link>
        <span className="nav-sep" aria-hidden="true">
          |
        </span>
        <Link href="/dashboard" className={navClass(pathname, "/dashboard")}>
          Dashboard
        </Link>
        <Link href="/websites" className={navClass(pathname, "/websites")}>
          Websites
        </Link>
        <Link href="/status" className={navClass(pathname, "/status")}>
          Status
        </Link>
        <AuthNav />
      </nav>
    </header>
  );
}

function navClass(pathname: string, href: string, exact = false): string | undefined {
  if (exact) {
    return pathname === href ? "nav-active" : undefined;
  }
  return pathname === href || pathname.startsWith(`${href}/`) ? "nav-active" : undefined;
}
