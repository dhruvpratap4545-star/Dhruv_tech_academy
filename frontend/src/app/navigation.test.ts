import { describe, expect, it } from "vitest";

import { ALL_NAV_ITEMS, NAVIGATION, visibleNavigation } from "@/app/navigation";
import { makeUser, roleAssignment } from "@/test/utils";

/**
 * The navigation registry.
 *
 * Two properties matter here. One is that people see only what they can open — the rule
 * the product promises. The other is quieter but caused a real defect: the registry has to
 * stay internally consistent, because `/audit` was once linked from two hand-written lists
 * with no route behind it and nothing could catch that by reading either list.
 */
describe("navigation registry", () => {
  it("gives a Super Admin every destination", () => {
    const owner = makeUser({
      roles: [roleAssignment("super_admin")],
      permissions: ["user:read", "institute:read", "audit:read", "role:read"],
    });
    const items = visibleNavigation(owner).flatMap((group) => group.items);
    expect(items).toHaveLength(ALL_NAV_ITEMS.length);
  });

  it("hides administration from a student rather than locking it", () => {
    const student = makeUser({
      roles: [roleAssignment("student", "inst-1")],
      permissions: ["class:read", "profile:read", "profile:update"],
    });
    const groups = visibleNavigation(student);
    const labels = groups.map((group) => group.label);

    expect(labels).not.toContain("Administration");
    // Not "present but disabled" — absent. A door you cannot open teaches nothing.
    const items = groups.flatMap((group) => group.items).map((item) => item.id);
    expect(items).toEqual(["dashboard", "my-access", "settings"]);
  });

  it("gives faculty people but not the audit log or roles", () => {
    const teacher = makeUser({
      roles: [roleAssignment("faculty", "inst-1", "branch-1")],
      permissions: ["user:read", "class:read", "institute:read"],
    });
    const items = visibleNavigation(teacher)
      .flatMap((group) => group.items)
      .map((item) => item.id);

    expect(items).toContain("users");
    expect(items).toContain("hierarchy");
    expect(items).not.toContain("audit");
    expect(items).not.toContain("roles");
  });

  it("drops a group entirely once it has no reachable items", () => {
    const nobody = makeUser({ roles: [], permissions: [] });
    expect(visibleNavigation(nobody).map((group) => group.label)).toEqual(["Overview", "Account"]);
  });

  it("has no duplicate ids or paths", () => {
    // Two entries sharing a path is how a nav item and its route drift apart unnoticed.
    expect(new Set(ALL_NAV_ITEMS.map((i) => i.id)).size).toBe(ALL_NAV_ITEMS.length);
    expect(new Set(ALL_NAV_ITEMS.map((i) => i.to)).size).toBe(ALL_NAV_ITEMS.length);
  });

  it("describes every destination, so My access can explain it", () => {
    for (const item of ALL_NAV_ITEMS) {
      expect(item.blurb.length).toBeGreaterThan(10);
      expect(item.to.startsWith("/")).toBe(true);
    }
    expect(NAVIGATION.every((group) => group.items.length > 0)).toBe(true);
  });
});
