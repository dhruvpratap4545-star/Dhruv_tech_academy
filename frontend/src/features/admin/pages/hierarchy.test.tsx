import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CreateInstitutePage } from "@/features/admin/pages/CreateInstitutePage";
import { InstitutesPage } from "@/features/admin/pages/InstitutesPage";
import type { CurrentUser } from "@/features/auth/types";
import type { Permission } from "@/lib/permissions";
import { makeUser, renderWithProviders, roleAssignment } from "@/test/utils";

/**
 * The hierarchy screens, against a fake API that answers by URL.
 *
 * `apiFetch` is replaced rather than the admin API module, so these also check that the
 * functions in api.ts send what the backend expects to the paths it serves.
 */
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<object>()),
  apiFetch: vi.fn(),
}));

const { apiFetch } = await import("@/lib/api");

const ORG_ID = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee";
const INSTITUTE_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const BRANCH_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
const SESSION_ID = "55555555-5555-4555-8555-555555555555";
const CLASS_ID = "cccccccc-cccc-4ccc-8ccc-cccccccccccc";
const STUDENT_ID = "99999999-9999-4999-8999-999999999999";

const page = <T,>(items: T[]) => ({ items, next_cursor: null, total: items.length });
const stamp = "2026-01-01T00:00:00Z";

const organisation = {
  id: ORG_ID,
  name: "JSPM Group",
  code: "JSPM",
  status: "active",
  contact_email: null,
  logo_url: null,
  institute_count: 1,
  created_at: stamp,
};
const institute = {
  id: INSTITUTE_ID,
  organisation_id: ORG_ID,
  name: "ABC College",
  code: "ABC",
  type: "college",
  status: "active",
  contact_email: null,
  logo_url: null,
  is_system: false,
  created_at: stamp,
};
const branch = {
  id: BRANCH_ID,
  institute_id: INSTITUTE_ID,
  name: "MCA",
  code: "MCA",
  city: null,
  address: null,
  status: "active",
  created_at: stamp,
};
const session = {
  id: SESSION_ID,
  institute_id: INSTITUTE_ID,
  name: "2026-27",
  start_date: "2026-06-01",
  end_date: "2027-05-31",
  is_current: true,
  created_at: stamp,
};
const classRow = {
  id: CLASS_ID,
  institute_id: INSTITUTE_ID,
  branch_id: BRANCH_ID,
  academic_session_id: SESSION_ID,
  name: "MCA 1st Year",
  code: "MCA1A",
  section: "A",
  status: "active",
  created_at: stamp,
};

let enrolled: { user_id: string; full_name: string; email: string; roll_no: string | null }[];

beforeEach(() => {
  HTMLDialogElement.prototype.showModal = vi.fn(function (this: HTMLDialogElement) {
    this.open = true;
  });
  HTMLDialogElement.prototype.close = vi.fn(function (this: HTMLDialogElement) {
    this.open = false;
  });
  enrolled = [];

  vi.mocked(apiFetch).mockReset();
  vi.mocked(apiFetch).mockImplementation(async (path: string, options = {}) => {
    const method = options.method ?? "GET";
    const url = path.split("?")[0];
    if (method === "GET") {
      if (url === "/organisations") return page([organisation]);
      if (url === "/institutes") return page([institute]);
      if (url === `/institutes/${INSTITUTE_ID}/branches`) return page([branch]);
      if (url === `/institutes/${INSTITUTE_ID}/sessions`) return page([session]);
      if (url === `/institutes/${INSTITUTE_ID}/classes`) return page([classRow]);
      if (url === `/institutes/${INSTITUTE_ID}/modules`) return [];
      if (url === `/classes/${CLASS_ID}/faculty`) return [];
      if (url === `/classes/${CLASS_ID}/students`) return enrolled;
      if (url === "/users")
        return page([
          {
            id: STUDENT_ID,
            email: "riya@abc.example",
            full_name: "Riya Sharma",
            phone: null,
            status: "active",
            last_login_at: null,
            created_at: stamp,
            roles: [roleAssignment("student", INSTITUTE_ID)],
          },
        ]);
    }
    if (method === "POST" && url === `/classes/${CLASS_ID}/students`) {
      enrolled = [
        { user_id: STUDENT_ID, full_name: "Riya Sharma", email: "riya@abc.example", roll_no: "7" },
      ];
      return {};
    }
    if (method === "POST" && url === "/institutes/with-admin") {
      return {
        institute,
        admin_user_id: "u1",
        admin_email: "priya@xyz.example",
        invitation_sent: true,
        setup_link: null,
      };
    }
    if (method === "POST") return {};
    throw new Error(`Unexpected ${method} ${path}`);
  });
});

function admin(permissions: Permission[]): CurrentUser {
  return makeUser({
    permissions,
    roles: [roleAssignment("institute_admin", INSTITUTE_ID)],
    institute_ids: [INSTITUTE_ID],
  });
}

function calls(method: string, url: string) {
  return vi
    .mocked(apiFetch)
    .mock.calls.filter(([path, options]) => (options?.method ?? "GET") === method && path === url);
}

describe("InstitutesPage", () => {
  it("groups institutes under their organisation and honours ?organisation=", async () => {
    renderWithProviders(<InstitutesPage />, {
      user: admin(["institute:read", "organisation:read", "branch:read"]),
      route: `/institutes?organisation=${ORG_ID}`,
    });
    const tree = await screen.findByRole("tree");
    const org = await within(tree).findByRole("treeitem", { name: /JSPM Group/ });
    await waitFor(() => expect(org).toHaveAttribute("aria-selected", "true"));
    expect(within(tree).getByRole("treeitem", { name: /ABC College/ })).toBeInTheDocument();
  });

  it("does not ask for levels the user cannot read", async () => {
    renderWithProviders(<InstitutesPage />, { user: admin(["institute:read"]) });
    await screen.findByRole("treeitem", { name: /ABC College/ });
    const paths = vi.mocked(apiFetch).mock.calls.map(([path]) => path.split("?")[0]);
    expect(paths).not.toContain(`/institutes/${INSTITUTE_ID}/branches`);
    expect(paths).not.toContain(`/institutes/${INSTITUTE_ID}/sessions`);
    expect(paths).not.toContain("/organisations");
  });

  it("adds a branch to the selected institute", async () => {
    renderWithProviders(<InstitutesPage />, {
      user: admin(["institute:read", "branch:read", "branch:create"]),
      route: `/institutes?institute=${INSTITUTE_ID}`,
    });
    await userEvent.click(await screen.findByRole("button", { name: /Add branch/ }));
    const dialog = await screen.findByRole("dialog", { name: "Add a branch" });
    await userEvent.type(within(dialog).getByRole("textbox", { name: "Branch name" }), "MBA");
    await userEvent.type(within(dialog).getByRole("textbox", { name: "Short code" }), "mba");
    await userEvent.click(within(dialog).getByRole("button", { name: "Add branch" }));

    await waitFor(() =>
      expect(calls("POST", `/institutes/${INSTITUTE_ID}/branches`)).toHaveLength(1),
    );
    expect(calls("POST", `/institutes/${INSTITUTE_ID}/branches`)[0]![1]!.body).toMatchObject({
      name: "MBA",
      code: "MBA",
    });
  });

  it("hides actions the user does not hold", async () => {
    renderWithProviders(<InstitutesPage />, {
      user: admin(["institute:read"]),
      route: `/institutes?institute=${INSTITUTE_ID}`,
    });
    await screen.findByRole("heading", { name: "ABC College" });
    expect(screen.queryByRole("button", { name: /Add branch/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Archive/ })).not.toBeInTheDocument();
  });

  it("enrols a student in a class and shows them on the roster", async () => {
    renderWithProviders(<InstitutesPage />, {
      user: admin([
        "institute:read",
        "branch:read",
        "session:read",
        "class:read",
        "enrollment:manage",
      ]),
    });
    await userEvent.click(await screen.findByRole("treeitem", { name: /MCA 1st Year/ }));

    const students = await screen.findByRole("region", { name: "Students" });
    await within(students).findByText(/Nobody is enrolled yet/);
    await within(students).findByRole("option", { name: /Riya Sharma/ });
    await userEvent.selectOptions(
      within(students).getByRole("combobox", { name: "Student" }),
      STUDENT_ID,
    );
    await userEvent.type(within(students).getByRole("textbox", { name: "Roll no" }), "7");
    await userEvent.click(within(students).getByRole("button", { name: "Enrol student" }));

    await waitFor(() => expect(calls("POST", `/classes/${CLASS_ID}/students`)).toHaveLength(1));
    expect(calls("POST", `/classes/${CLASS_ID}/students`)[0]![1]!.body).toEqual({
      user_id: STUDENT_ID,
      roll_no: "7",
    });
    expect(
      await within(students).findByRole("button", { name: "Remove Riya Sharma" }),
    ).toBeInTheDocument();
  });

  it("does not fetch the student roster without enrollment:manage", async () => {
    renderWithProviders(<InstitutesPage />, {
      user: admin(["institute:read", "branch:read", "session:read", "class:read"]),
    });
    await userEvent.click(await screen.findByRole("treeitem", { name: /MCA 1st Year/ }));
    await screen.findByRole("region", { name: "Faculty" });
    expect(screen.queryByRole("region", { name: "Students" })).not.toBeInTheDocument();
    expect(calls("GET", `/classes/${CLASS_ID}/students`)).toHaveLength(0);
  });
});

describe("CreateInstitutePage", () => {
  async function fill() {
    await userEvent.type(screen.getByRole("textbox", { name: "Institute name" }), "XYZ School");
    await userEvent.type(screen.getByRole("textbox", { name: "Short code" }), "XYZ");
    await userEvent.type(screen.getByRole("textbox", { name: "Full name" }), "Priya Shah");
    await userEvent.type(
      screen.getByRole("textbox", { name: "Email address" }),
      "priya@xyz.example",
    );
  }

  it("sends the Organisation Admin's own organisation", async () => {
    renderWithProviders(<CreateInstitutePage />, {
      user: makeUser({
        permissions: ["institute:create", "organisation:read"],
        roles: [roleAssignment("org_admin", null, null, { organisation_id: ORG_ID })],
      }),
    });
    const select = await screen.findByRole("combobox", { name: "Organisation" });
    await screen.findByRole("option", { name: "JSPM Group" });
    // Required for them, and no standalone option.
    expect(within(select).queryByRole("option", { name: /standalone/i })).not.toBeInTheDocument();
    expect(select).toHaveValue(ORG_ID);

    await fill();
    await userEvent.click(screen.getByRole("button", { name: "Create institute" }));
    await waitFor(() => expect(calls("POST", "/institutes/with-admin")).toHaveLength(1));
    expect(calls("POST", "/institutes/with-admin")[0]![1]!.body).toMatchObject({
      institute: { name: "XYZ School", organisation_id: ORG_ID },
      admin_email: "priya@xyz.example",
    });
  });

  it("lets platform staff leave it standalone", async () => {
    renderWithProviders(<CreateInstitutePage />, {
      user: makeUser({
        permissions: ["institute:create", "organisation:read"],
        roles: [roleAssignment("platform_admin")],
      }),
    });
    await screen.findByRole("option", { name: "JSPM Group" });
    expect(screen.getByRole("combobox", { name: "Organisation" })).toHaveValue("");

    await fill();
    await userEvent.click(screen.getByRole("button", { name: "Create institute" }));
    await waitFor(() => expect(calls("POST", "/institutes/with-admin")).toHaveLength(1));
    const body = calls("POST", "/institutes/with-admin")[0]![1]!.body as {
      institute: Record<string, unknown>;
    };
    expect(body.institute.organisation_id).toBeUndefined();
  });
});
