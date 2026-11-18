"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { AuthUser, getCurrentUser, logoutAccount } from "@/lib/auth";

export function AuthNav() {
  const router = useRouter();
  const [user, setUser] = useState<AuthUser | null | undefined>(undefined);

  useEffect(() => {
    const controller = new AbortController();
    getCurrentUser(controller.signal)
      .then(setUser)
      .catch(() => setUser(null));
    return () => controller.abort();
  }, []);

  async function onLogout() {
    try {
      await logoutAccount();
    } catch {
      // Still clear local UI state.
    }
    setUser(null);
    router.push("/login");
    router.refresh();
  }

  if (user === undefined) {
    return <span className="hint tight">…</span>;
  }

  if (!user) {
    return (
      <>
        <Link href="/login">Login</Link>
        <Link href="/register">Register</Link>
      </>
    );
  }

  return (
    <>
      <span className="nav-user" title={user.email}>
        {user.email}
      </span>
      <button type="button" className="linkish" onClick={onLogout}>
        Log out
      </button>
    </>
  );
}
