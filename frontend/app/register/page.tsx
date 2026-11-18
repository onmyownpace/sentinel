import Link from "next/link";

import { AuthForm } from "@/components/AuthForm";

export default function RegisterPage() {
  return (
    <main>
      <h1>Register</h1>
      <p>Create a local email/password account on this development machine.</p>
      <AuthForm mode="register" />
      <p className="hint">
        Already registered? <Link href="/login">Sign in</Link>.
      </p>
    </main>
  );
}
