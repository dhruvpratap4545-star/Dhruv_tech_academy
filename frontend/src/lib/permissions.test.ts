import { describe, expect, it } from "vitest";

import {
  can,
  canAny,
  highestRank,
  isFacultyOnly,
  isPlatformStaff,
  ROLE_RANK,
} from "@/lib/permissions";
import { makeUser, roleAssignment } from "@/test/utils";

describe("can", () => {
  it("is true only for a permission the user actually holds", () => {
    const user = makeUser({ permissions: ["user:read", "user:invite"] });
    expect(can(user, "user:invite")).toBe(true);
    expect(can(user, "institute:create")).toBe(false);
  });

  it("is false when nobody is signed in", () => {
    expect(can(null, "user:read")).toBe(false);
    expect(can(undefined, "user:read")).toBe(false);
  });
});

describe("canAny", () => {
  it("passes when at least one permission is held", () => {
    const user = makeUser({ permissions: ["audit:read"] });
    expect(canAny(user, ["user:invite", "audit:read"])).toBe(true);
    expect(canAny(user, ["user:invite", "institute:create"])).toBe(false);
  });
});

describe("isPlatformStaff", () => {
  it("is true for a role held at platform scope", () => {
    expect(isPlatformStaff(makeUser({ roles: [roleAssignment("super_admin")] }))).toBe(true);
  });

  it("is false for a role scoped to one institute", () => {
    const user = makeUser({ roles: [roleAssignment("institute_admin", "inst-a")] });
    expect(isPlatformStaff(user)).toBe(false);
  });
});

describe("highestRank", () => {
  it("returns the most senior role held", () => {
    const user = makeUser({
      roles: [roleAssignment("student", "inst-a"), roleAssignment("institute_admin", "inst-a")],
    });
    expect(highestRank(user)).toBe(ROLE_RANK.institute_admin);
  });

  it("is zero when no role is held", () => {
    expect(highestRank(makeUser())).toBe(0);
  });
});

describe("isFacultyOnly", () => {
  it("is true for a teacher, who must name their own classes when inviting", () => {
    const user = makeUser({ roles: [roleAssignment("faculty", "inst-a", "branch-a")] });
    expect(isFacultyOnly(user)).toBe(true);
  });

  it("is false for anyone senior to faculty", () => {
    const user = makeUser({ roles: [roleAssignment("branch_admin", "inst-a", "branch-a")] });
    expect(isFacultyOnly(user)).toBe(false);
  });
});
