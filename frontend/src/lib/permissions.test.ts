import { describe, expect, it } from "vitest";

import {
  can,
  canAny,
  highestRank,
  isFacultyOnly,
  isLearnerOrParentOnly,
  isOrganisationAdmin,
  isPlatformStaff,
  picksInstitute,
  roleAssignmentKey,
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

  it("is false for an organisation-wide role, which names no institute either", () => {
    const user = makeUser({
      roles: [roleAssignment("org_admin", null, null, { organisation_id: "org-a" })],
    });
    expect(isPlatformStaff(user)).toBe(false);
    expect(isOrganisationAdmin(user)).toBe(true);
  });

  it("is true for platform staff who also hold an organisation role", () => {
    const user = makeUser({
      roles: [
        roleAssignment("org_admin", null, null, { organisation_id: "org-a" }),
        roleAssignment("platform_admin"),
      ],
    });
    expect(isPlatformStaff(user)).toBe(true);
  });
});

describe("picksInstitute", () => {
  it("is false for somebody pinned to one institute", () => {
    const user = makeUser({
      roles: [roleAssignment("institute_admin", "inst-a")],
      institute_ids: ["inst-a"],
    });
    expect(picksInstitute(user)).toBe(false);
  });

  it("is true for an organisation admin and for anybody in several institutes", () => {
    const orgAdmin = makeUser({
      roles: [roleAssignment("org_admin", null, null, { organisation_id: "org-a" })],
    });
    const twoColleges = makeUser({
      roles: [
        roleAssignment("faculty", "inst-a", "b-1"),
        roleAssignment("faculty", "inst-b", "b-2"),
      ],
      institute_ids: ["inst-a", "inst-b"],
    });
    expect(picksInstitute(orgAdmin)).toBe(true);
    expect(picksInstitute(twoColleges)).toBe(true);
  });
});

describe("isLearnerOrParentOnly", () => {
  it("is true only when every role is a student's or a parent's", () => {
    const family = makeUser({
      roles: [roleAssignment("student", "inst-a"), roleAssignment("parent", "inst-a")],
    });
    const teacherParent = makeUser({
      roles: [roleAssignment("parent", "inst-a"), roleAssignment("faculty", "inst-a", "b-1")],
    });
    expect(isLearnerOrParentOnly(family)).toBe(true);
    expect(isLearnerOrParentOnly(teacherParent)).toBe(false);
    expect(isLearnerOrParentOnly(makeUser())).toBe(false);
  });
});

describe("roleAssignmentKey", () => {
  it("tells apart the same role held in two organisations", () => {
    const a = roleAssignment("org_admin", null, null, { organisation_id: "org-a" });
    const b = roleAssignment("org_admin", null, null, { organisation_id: "org-b" });
    expect(roleAssignmentKey(a)).not.toBe(roleAssignmentKey(b));
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
