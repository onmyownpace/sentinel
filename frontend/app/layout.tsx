import type { Metadata } from "next";
import type { ReactNode } from "react";

import { PublicShellBanner } from "@/components/PublicShellBanner";
import { SiteHeader } from "@/components/SiteHeader";

import "./globals.css";

export const metadata: Metadata = {
  title: "Sentinel",
  description: "Website testing and monitoring",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <SiteHeader />
        <PublicShellBanner />
        {children}
      </body>
    </html>
  );
}
