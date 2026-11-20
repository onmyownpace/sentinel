"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { AuthNav } from "@/components/AuthNav";
import { getDeploymentMode } from "@/lib/deployment";

export function SiteHeader() {
  const pathname = usePathname();
  const [publicShell, setPublicShell] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    getDeploymentMode(AbortSignal.any([controller.signal, AbortSignal.timeout(8000)])).then(
      (mode) => {
        if (!controller.signal.aborted) {
          setPublicShell(mode.publicShell);
        }
      },
    );
    return () => controller.abort();
  }, []);

  const onLanding = pathname === "/";

  return (
    <header className={onLanding ? "site-header site-header-landing" : "site-header"}>
      <Link href="/" className="brand">
        Sentinel
      </Link>
      <nav aria-label="Primary">
        {publicShell ? (
          <>
            <Link href="/demo" className={navClass(pathname, "/demo")}>
              Try the demo
            </Link>
            <Link href="/dashboard" className={navClass(pathname, "/dashboard")}>
              Dashboard
            </Link>
            <Link href="/websites" className={navClass(pathname, "/websites")}>
              Websites
            </Link>
          </>
        ) : (
          <>
            <Link href="/dashboard" className={navClass(pathname, "/dashboard")}>
              Dashboard
            </Link>
            <Link href="/websites" className={navClass(pathname, "/websites")}>
              Websites
            </Link>
            <AuthNav />
          </>
        )}
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
