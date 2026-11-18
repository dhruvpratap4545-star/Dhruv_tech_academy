// Writes the nginx directive that sends the app shell's Content-Security-Policy.
//
// Mirrors build_csp() in backend/app/core/spa.py: the policy allows exactly the inline
// scripts the built index.html contains, hashed at build time, so editing the theme script
// in index.html cannot quietly break it in production.
//
//   node scripts/build-csp.mjs dist/index.html > csp.conf
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";

const html = readFileSync(process.argv[2], "utf8");
const hashes = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(
  ([, body]) => `'sha256-${createHash("sha256").update(body, "utf8").digest("base64")}'`,
);

const policy = [
  "default-src 'self'",
  "connect-src 'self' https://storage.googleapis.com",
  "img-src 'self' data:",
  "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
  "font-src 'self' https://fonts.gstatic.com",
  `script-src 'self' ${hashes.join(" ")}`.trim(),
  "object-src 'none'",
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
].join("; ");

process.stdout.write(`add_header Content-Security-Policy "${policy}" always;\n`);
