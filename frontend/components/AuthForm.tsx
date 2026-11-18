"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { AuthApiError, loginAccount, registerAccount } from "@/lib/auth";
import { getDeploymentMode } from "@/lib/deployment";

type Mode = "login" | "register";

export function AuthForm({ mode }: { mode: Mode }) {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [registrationOpen, setRegistrationOpen] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    getDeploymentMode(controller.signal).then((m) => setRegistrationOpen(m.registrationOpen));
    return () => controller.abort();
  }, []);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mode === "login") {
        await loginAccount(email, password);
      } else {
        await registerAccount(email, password);
      }
      router.push("/dashboard");
      router.refresh();
    } catch (err) {
      setError(err instanceof AuthApiError ? err.message : "Sign-in failed.");
    } finally {
      setBusy(false);
    }
  }

  if (mode === "register" && !registrationOpen) {
    return (
      <section className="stack card" aria-label="Registration closed">
        <h2>Create account</h2>
        <p className="banner warn" role="status">
          Public registration is closed on this deployment. Sign in with the portfolio demo
          account, or run Sentinel locally to register freely.
        </p>
        <p className="hint tight">
          <a href="/login">Sign in</a>
        </p>
      </section>
    );
  }

  return (
    <form className="stack card" onSubmit={onSubmit} noValidate>
      <h2>{mode === "login" ? "Sign in" : "Create account"}</h2>
      <p className="hint tight">
        Email and password only. Sessions use an HttpOnly cookie named{" "}
        <code>sentinel_session</code>.
      </p>
      {error ? (
        <p className="banner warn" role="alert">
          {error}
        </p>
      ) : null}
      <label>
        Email
        <input
          type="email"
          autoComplete="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          required
        />
      </label>
      <label>
        Password
        <input
          type="password"
          autoComplete={mode === "login" ? "current-password" : "new-password"}
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          minLength={8}
          required
        />
      </label>
      <div className="actions">
        <button type="submit" className="primary" disabled={busy}>
          {busy ? "Working…" : mode === "login" ? "Sign in" : "Register"}
        </button>
      </div>
    </form>
  );
}
