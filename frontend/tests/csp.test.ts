import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * Keeps the deployed Content-Security-Policy honest.
 *
 * The CSP lives in `render.yaml` and is only enforced once the app is on Render, so every
 * mistake in it is invisible here and silent there: a blocked font renders in Arial, a
 * blocked script simply does not run, and nothing in the build or the test suite notices.
 *
 * The inline theme script is the sharpest edge. It is allowed by SHA-256 hash rather than
 * `'unsafe-inline'`, which is right — it means that one script is permitted and no injected
 * one is — but it also means editing the script by a single character invalidates the hash.
 * The theme would then stop applying before first paint, in production only, with no error
 * anyone would see. This test turns that into a failure here instead.
 */

const root = resolve(__dirname, "../..");  // frontend/tests -> repo root

/**
 * Read the deployed bytes, not the working-copy bytes.
 *
 * `.gitattributes` normalises the repository to LF, so Render checks out LF and serves LF.
 * A Windows working copy holds CRLF, and hashing that gives a different, wrong value — the
 * CSP would then look correct on this machine and be broken in production, which is the
 * precise failure this file exists to prevent.
 */
function readAsDeployed(path: string): string {
  return readFileSync(resolve(root, path), "utf8").split("\r\n").join("\n");
}

const indexHtml = readAsDeployed("frontend/index.html");
const renderYaml = readAsDeployed("render.yaml");

/** Inline scripts only — a `src=` tag is covered by `'self'`, not by a hash. */
function inlineScripts(html: string): string[] {
  return [...html.matchAll(/<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/g)].map((m) => m[1]!);
}

function sha256(body: string): string {
  return `sha256-${createHash("sha256").update(body).digest("base64")}`;
}

/** The CSP is a folded YAML scalar, so rejoin it before matching. */
const csp = (() => {
  const block = renderYaml.split("name: Content-Security-Policy")[1] ?? "";
  const value = block.split("value: >-")[1] ?? "";
  return value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .slice(0, 9)
    .join(" ");
})();

describe("deployed Content-Security-Policy", () => {
  it("allows exactly the inline scripts the page ships", () => {
    const scripts = inlineScripts(indexHtml);
    expect(scripts, "index.html should carry the theme script").toHaveLength(1);

    for (const body of scripts) {
      expect(
        csp,
        "The inline script in index.html changed, so its CSP hash in render.yaml is stale. " +
          `Replace the script-src hash with: '${sha256(body)}'`,
      ).toContain(sha256(body));
    }
  });

  it("never falls back to allowing any inline script", () => {
    const scriptSrc = csp.match(/script-src[^;]*/)?.[0] ?? "";
    expect(scriptSrc, "hashing one script is the point; unsafe-inline undoes it").not.toContain(
      "unsafe-inline",
    );
  });

  it("allows every external origin the page loads from", () => {
    const origins = [...indexHtml.matchAll(/https:\/\/[a-z0-9.-]+/g)].map((m) => m[0]);
    for (const origin of new Set(origins)) {
      expect(csp, `index.html loads from ${origin}, which the CSP must permit`).toContain(origin);
    }
  });

  it("still points connect-src at the API", () => {
    // The app is useless if it cannot reach its own backend, and this is the one
    // directive a domain change would silently invalidate.
    expect(csp).toMatch(/connect-src[^;]*https:\/\/api\.dhruvonlineacademy\.com/);
  });

  it("keeps the clickjacking and base-tag protections", () => {
    expect(csp).toContain("frame-ancestors 'none'");
    expect(csp).toContain("base-uri 'self'");
    expect(csp).toContain("form-action 'self'");
  });
});
