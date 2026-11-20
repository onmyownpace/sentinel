import Link from "next/link";

/** Secondary links only — diagnostics stay out of primary product nav. */
export function SiteFooter() {
  return (
    <footer className="site-footer">
      <p className="hint tight">
        <Link href="/status">Diagnostics</Link>
        {" · "}
        API / database status for operators
      </p>
    </footer>
  );
}
