import path from "node:path";
import { fileURLToPath } from "node:url";

import type { NextConfig } from "next";

// Next.js looks upward for a lockfile when it infers the workspace root.
// Pin the root to this directory so a package-lock.json in a parent folder
// is not treated as the project.
const frontendRoot = path.dirname(fileURLToPath(import.meta.url));

const nextConfig: NextConfig = {
  reactStrictMode: true,
  turbopack: {
    root: frontendRoot,
  },
};

export default nextConfig;
