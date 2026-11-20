"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { AuthNav } from "@/components/AuthNav";

export function SiteHeader() {
  const pathname = usePathname();

  return (
    <header className="site-header">
      <Link href="/dashboard" className="brand">
        Sentinel
      </Link>
      <nav aria-label="Primary">
        <Link href="/dashboard" className={navClass(pathname, "/dashboard")}>
          Dashboard
        </Link>
        <Link href="/websites" className={navClass(pathname, "/websites")}>
          Websites
        </Link>
        <span className="nav-sep" aria-hidden="true">
          |
        </span>
        <Link href="/" className={navClass(pathname, "/", true)}>
          Demo
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
