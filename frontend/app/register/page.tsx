"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { AuthForm } from "@/components/AuthForm";
import { getDeploymentMode } from "@/lib/deployment";

export default function RegisterPage() {
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [registrationOpen, setRegistrationOpen] = useState(false);

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
      setRegistrationOpen(mode.registrationOpen);
      setReady(true);
    });
    return () => controller.abort();
  }, [router]);

  if (!ready) {
    return (
      <main>
        <p className="hint">Loading…</p>
      </main>
    );
  }

  if (!registrationOpen) {
    return (
      <main>
        <h1>Registration closed</h1>
        <p>
          Public registration is closed on this deployment.{" "}
          <Link href="/demo">Try the demo</Link> with no account, or run Sentinel locally to
          register freely.
        </p>
      </main>
    );
  }

  return (
    <main>
      <h1>Register</h1>
      <p>Create a local account for your monitoring workspace.</p>
      <AuthForm mode="register" />
      <p className="hint">
        Already registered? <Link href="/login">Sign in</Link>.
      </p>
    </main>
  );
}
