import Link from "next/link";

import { AuthForm } from "@/components/AuthForm";

export default function LoginPage() {
  return (
    <main>
      <h1>Login</h1>
      <p>
        Sign in to manage your registry and dashboard. Dev seed account:{" "}
        <code>dev@sentinel.local</code> / <code>dev-password-change-me</code>.
      </p>
      <AuthForm mode="login" />
      <p className="hint">
        No account yet? <Link href="/register">Register</Link>.
      </p>
    </main>
  );
}
