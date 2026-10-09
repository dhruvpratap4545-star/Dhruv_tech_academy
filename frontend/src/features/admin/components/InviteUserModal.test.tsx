import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { InviteUserModal } from "@/features/admin/components/InviteUserModal";
import { makeUser, renderWithProviders, roleAssignment } from "@/test/utils";

vi.mock("@/features/auth/api", () => ({
  meKey: ["me"],
  fetchAssignableRoles: vi.fn(),
}));

vi.mock("@/features/admin/api", () => ({
  userKeys: { all: ["users"], list: () => ["users", "list"] },
  instituteKeys: {
    all: ["institutes"],
    list: () => ["institutes", "list"],
    branches: (id: string) => ["institutes", id, "branches"],
    classes: (id: string, b?: string) => ["institutes", id, "classes", b ?? "all"],
  },
  inviteUser: vi.fn(),
  fetchInstitutes: vi.fn(),
  fetchBranches: vi.fn(),
  fetchClasses: vi.fn(),
}));

const { fetchAssignableRoles } = await import("@/features/auth/api");
const { fetchBranches, fetchClasses, fetchInstitutes, inviteUser } =
  await import("@/features/admin/api");

const INSTITUTE_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const BRANCH_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
const CLASS_ID = "cccccccc-cccc-4ccc-8ccc-cccccccccccc";

/** HTMLDialogElement is not implemented in jsdom. */
beforeEach(() => {
  HTMLDialogElement.prototype.showModal = vi.fn(function (this: HTMLDialogElement) {
    this.open = true;
  });
  HTMLDialogElement.prototype.close = vi.fn(function (this: HTMLDialogElement) {
    this.open = false;
  });

  vi.mocked(fetchInstitutes).mockResolvedValue({ items: [], next_cursor: null, total: 0 });
  vi.mocked(fetchBranches).mockResolvedValue({
    items: [
      {
        id: BRANCH_ID,
        institute_id: INSTITUTE_ID,
        name: "MCA",
        code: "MCA",
        city: null,
        address: null,
        status: "active",
        created_at: "2026-01-01T00:00:00Z",
      },
    ],
    next_cursor: null,
    total: 0,
  });
  vi.mocked(fetchClasses).mockResolvedValue({
    items: [
      {
        id: CLASS_ID,
        institute_id: INSTITUTE_ID,
        branch_id: BRANCH_ID,
        academic_session_id: "s1",
        name: "MCA 1st Year",
        code: "MCA1A",
        section: "A",
        status: "active",
        created_at: "2026-01-01T00:00:00Z",
      },
    ],
    next_cursor: null,
    total: 0,
  });
  vi.mocked(inviteUser).mockResolvedValue({
    user: {
      id: "u1",
      email: "ravi@example.com",
      full_name: "Ravi Kumar",
      phone: null,
      status: "invited",
      last_login_at: null,
      created_at: "2026-01-01T00:00:00Z",
      roles: [],
    },
    invitation_sent: true,
  });
});

const instituteAdmin = makeUser({
  permissions: ["user:invite", "role:assign"],
  roles: [roleAssignment("institute_admin", INSTITUTE_ID)],
  institute_ids: [INSTITUTE_ID],
});

function open(user = instituteAdmin) {
  return renderWithProviders(<InviteUserModal open onClose={() => {}} />, { user });
}

/**
 * The select renders immediately with a "Loading roles…" placeholder, so finding it is not
 * enough — the test has to wait until the roles query has actually populated it.
 */
async function roleSelect() {
  const select = await screen.findByRole("combobox", { name: "Role" });
  await waitFor(() => expect(select).toBeEnabled());
  return select;
}

describe("InviteUserModal", () => {
  it("offers exactly the roles the backend says the user may give", async () => {
    // The server has already filtered this list by rank (PRD §3.1). The form must not
    // widen it, and must not narrow it either.
    vi.mocked(fetchAssignableRoles).mockResolvedValue([
      { key: "branch_admin", name: "Branch Admin", scope_level: "branch", rank: 50 },
      { key: "faculty", name: "Faculty", scope_level: "branch", rank: 30 },
      { key: "student", name: "Student", scope_level: "institute", rank: 10 },
    ]);

    open();
    const options = within(await roleSelect())
      .getAllByRole("option")
      .map((option) => option.textContent);

    expect(options).toContain("Branch Admin");
    expect(options).toContain("Faculty");
    expect(options).toContain("Student");
    // An Institute Admin must never be offered their own role or anything above it.
    expect(options).not.toContain("Institute Admin");
    expect(options).not.toContain("Platform Admin");
    expect(options).not.toContain("Super Admin");
  });

  it("says so when the user may not give out any role at all", async () => {
    vi.mocked(fetchAssignableRoles).mockResolvedValue([]);
    open();
    expect(
      await screen.findByText(/do not have permission to give out any roles/i),
    ).toBeInTheDocument();
  });

  it("asks for a branch when the chosen role is branch-scoped", async () => {
    vi.mocked(fetchAssignableRoles).mockResolvedValue([
      { key: "branch_admin", name: "Branch Admin", scope_level: "branch", rank: 50 },
      { key: "student", name: "Student", scope_level: "institute", rank: 10 },
    ]);

    open();
    const select = await roleSelect();

    expect(screen.queryByRole("combobox", { name: "Branch" })).not.toBeInTheDocument();
    await userEvent.selectOptions(select, "branch_admin");
    expect(await screen.findByRole("combobox", { name: "Branch" })).toBeInTheDocument();
  });

  it("does not ask for a branch for an institute-scoped role", async () => {
    vi.mocked(fetchAssignableRoles).mockResolvedValue([
      { key: "student", name: "Student", scope_level: "institute", rank: 10 },
    ]);

    open();
    await userEvent.selectOptions(await roleSelect(), "student");
    expect(screen.queryByRole("combobox", { name: "Branch" })).not.toBeInTheDocument();
  });

  it("offers classes for a student so a teacher can attach them to their own class", async () => {
    vi.mocked(fetchAssignableRoles).mockResolvedValue([
      { key: "student", name: "Student", scope_level: "institute", rank: 10 },
    ]);

    open();
    await userEvent.selectOptions(await roleSelect(), "student");
    expect(await screen.findByText(/MCA 1st Year/)).toBeInTheDocument();
  });

  it("will not submit without a name, an email and a role", async () => {
    vi.mocked(fetchAssignableRoles).mockResolvedValue([
      { key: "student", name: "Student", scope_level: "institute", rank: 10 },
    ]);

    open();
    await userEvent.click(await screen.findByRole("button", { name: /Send invitation/i }));

    expect(await screen.findByText(/Enter their full name/i)).toBeInTheDocument();
    expect(screen.getByText(/Enter your email address|valid email/i)).toBeInTheDocument();
    expect(screen.getByText("Please choose a role.")).toBeInTheDocument();
    expect(inviteUser).not.toHaveBeenCalled();
  });

  it("sends the invitation with the chosen role and scope", async () => {
    vi.mocked(fetchAssignableRoles).mockResolvedValue([
      { key: "student", name: "Student", scope_level: "institute", rank: 10 },
    ]);

    open();
    await userEvent.type(await screen.findByRole("textbox", { name: "Full name" }), "Ravi Kumar");
    await userEvent.type(
      screen.getByRole("textbox", { name: "Email address" }),
      "ravi@example.com",
    );
    await userEvent.selectOptions(await roleSelect(), "student");
    await userEvent.click(screen.getByRole("button", { name: /Send invitation/i }));

    await waitFor(() => expect(inviteUser).toHaveBeenCalled());
    expect(vi.mocked(inviteUser).mock.calls[0]![0]).toMatchObject({
      full_name: "Ravi Kumar",
      email: "ravi@example.com",
      role_key: "student",
      institute_id: INSTITUTE_ID,
    });
  });

  it("shows the server's refusal rather than swallowing it", async () => {
    // The backend is the real check: if it says no, the user has to be told why.
    const { ApiError } = await import("@/lib/api");
    vi.mocked(fetchAssignableRoles).mockResolvedValue([
      { key: "student", name: "Student", scope_level: "institute", rank: 10 },
    ]);
    vi.mocked(inviteUser).mockRejectedValue(
      new ApiError(403, "FORBIDDEN", "You cannot give someone a role at or above your own level."),
    );

    open();
    await userEvent.type(await screen.findByRole("textbox", { name: "Full name" }), "Ravi Kumar");
    await userEvent.type(
      screen.getByRole("textbox", { name: "Email address" }),
      "ravi@example.com",
    );
    await userEvent.selectOptions(await roleSelect(), "student");
    await userEvent.click(screen.getByRole("button", { name: /Send invitation/i }));

    expect(await screen.findByText(/at or above your own level/i)).toBeInTheDocument();
  });
});
