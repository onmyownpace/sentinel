import type { Metadata } from "next";
import type { ReactNode } from "react";
import { Figtree, Syne } from "next/font/google";

import { SiteFooter } from "@/components/SiteFooter";
import { SiteHeader } from "@/components/SiteHeader";

import "./globals.css";

const bodyFont = Figtree({
  subsets: ["latin"],
  variable: "--font-figtree",
  display: "swap",
});

const displayFont = Syne({
  subsets: ["latin"],
  variable: "--font-syne",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Sentinel",
  description: "Website monitoring with failure analysis",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`${bodyFont.variable} ${displayFont.variable}`}>
      <body>
        <SiteHeader />
        {children}
        <SiteFooter />
      </body>
    </html>
  );
}
