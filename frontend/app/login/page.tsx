"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { AuthForm } from "@/components/AuthForm";
import { getDeploymentMode } from "@/lib/deployment";

export default function LoginPage() {
  const router = useRouter();
  const [publicShell, setPublicShell] = useState<boolean | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    getDeploymentMode(controller.signal).then((mode) => {
      if (controller.signal.aborted) {
        return;
      }
      if (mode.publicShell) {
        router.replace("/demo");
        return;
      }
      setPublicShell(false);
    });
    return () => controller.abort();
  }, [router]);

  if (publicShell === null) {
    return (
      <main>
        <p className="hint">Loading…</p>
      </main>
    );
  }

  return (
    <main>
      <h1>Login</h1>
      <p>Sign in to manage your registry and dashboard on a local deployment.</p>
      <AuthForm mode="login" />
      <p className="hint">
        Prefer the portfolio path? <Link href="/demo">Try the demo</Link> with no account.
      </p>
    </main>
  );
}
