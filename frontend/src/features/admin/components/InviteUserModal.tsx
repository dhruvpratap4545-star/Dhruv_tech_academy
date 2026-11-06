import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";

import { Alert } from "@/components/Alert";
import type { InviteResult } from "@/features/admin/components/InviteLink";
import { Button } from "@/components/Button";
import { Field, SelectField, TextField } from "@/components/Field";
import { Modal } from "@/components/Modal";
import { fetchAssignableRoles } from "@/features/auth/api";
import { email as emailSchema } from "@/features/auth/schemas";
import type { RoleKey } from "@/features/auth/types";
import { useCurrentUser } from "@/features/auth/useAuth";
import {
  isFacultyOnly,
  organisationIds,
  picksInstitute,
  ROLE_REQUIREMENTS,
} from "@/lib/permissions";
import {
  fetchBranches,
  fetchClasses,
  fetchInstitutes,
  fetchOrganisations,
  instituteKeys,
  inviteUser,
  organisationKeys,
  userKeys,
} from "@/features/admin/api";

const schema = z.object({
  full_name: z.string().min(2, "Enter their full name.").max(120, "That name is too long."),
  email: emailSchema,
  role_key: z.string().min(1, "Please choose a role."),
  organisation_id: z.string(),
  institute_id: z.string(),
  branch_id: z.string(),
  class_ids: z.array(z.string()),
});

type Values = z.infer<typeof schema>;

/**
 * Invite a user (PRD §4.2).
 *
 * The role list comes from `GET /users/roles/catalogue`, which the **backend** has already
 * filtered to roles strictly below the caller's own rank. Deriving it on the client would
 * mean reimplementing PRD §3.1 in two places and letting them drift — and the backend
 * rejects anything it did not offer, so a client-side guess would only produce confusing
 * 403s. The form shapes itself to the chosen role; the server is still the real check.
 *
 * Which scope fields appear comes from the chosen role's `scope_level` in that same
 * catalogue, so a custom role is asked for exactly what it needs — a hardcoded table of
 * built-in keys gave custom roles no fields at all, and the server then refused them.
 */
export function InviteUserModal({
  open,
  onClose,
  onInvited,
}: {
  open: boolean;
  onClose: () => void;
  /** Called with the invited person's name so the page can confirm what was sent. */
  onInvited?: (result: InviteResult) => void;
}) {
  const user = useCurrentUser();
  const queryClient = useQueryClient();
  // Platform staff, organisation admins and anybody in several institutes choose one;
  // somebody pinned to a single institute has it filled in.
  const choosesInstitute = picksInstitute(user);
  // A teacher's authority is the classes they teach, so the server wants one named.
  const facultyInviter = isFacultyOnly(user);

  /**
   * Empty the form on the way out, not only after a successful send.
   *
   * Without this the dialog reopened holding whatever was last typed — including the red
   * error messages from a failed attempt, as though it had just been submitted again.
   * The dangerous version of that is the ordinary one: mistype an address, close the
   * dialog, open it again, and the wrong address is sitting there pre-filled, next to a
   * name that looks right.
   */
  const close = () => {
    form.reset();
    submit.reset();
    onClose();
  };

  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      full_name: "",
      email: "",
      role_key: "",
      organisation_id: "",
      institute_id: "",
      branch_id: "",
      class_ids: [],
    },
  });

  // `useWatch` rather than `form.watch()`: watch() returns a fresh function each render,
  // which the React Compiler cannot memoise, so it bails out of optimising this component
  // entirely. useWatch subscribes properly and keeps the compiler engaged.
  const control = form.control;
  const roleKey = (useWatch({ control, name: "role_key" }) ?? "") as RoleKey | "";
  const organisationId = useWatch({ control, name: "organisation_id" }) ?? "";
  const instituteId = useWatch({ control, name: "institute_id" }) ?? "";
  const branchId = useWatch({ control, name: "branch_id" }) ?? "";
  const selectedClasses = useWatch({ control, name: "class_ids" }) ?? [];

  const roles = useQuery({
    queryKey: ["assignable-roles", "invite"],
    queryFn: () => fetchAssignableRoles("invite"),
    enabled: open,
  });

  const chosen = roles.data?.find((role) => role.key === roleKey);
  const needsOrganisation = chosen?.scope_level === "organisation";
  const needsInstitute = chosen?.scope_level === "institute" || chosen?.scope_level === "branch";
  const needsBranch = chosen?.scope_level === "branch";
  // Classes are offered for the built-ins that sit in classes (students, teachers), and
  // demanded whenever the inviter is a teacher.
  const classMode: "none" | "optional" | "required" = !needsInstitute
    ? "none"
    : facultyInviter
      ? "required"
      : (ROLE_REQUIREMENTS[roleKey]?.classes ?? "none");

  const organisations = useQuery({
    queryKey: organisationKeys.list(),
    queryFn: ({ signal }) => fetchOrganisations(signal),
    enabled: open && needsOrganisation,
  });

  const institutes = useQuery({
    queryKey: instituteKeys.list(),
    queryFn: ({ signal }) => fetchInstitutes(signal),
    enabled: open && choosesInstitute && needsInstitute,
  });

  const branches = useQuery({
    queryKey: instituteKeys.branches(instituteId),
    queryFn: ({ signal }) => fetchBranches(instituteId, signal),
    enabled: open && Boolean(instituteId) && needsBranch,
  });

  // For a teacher the server narrows this to the classes they teach.
  const classes = useQuery({
    queryKey: instituteKeys.classes(instituteId, branchId || undefined),
    queryFn: ({ signal }) => fetchClasses(instituteId, branchId || undefined, signal),
    enabled: open && Boolean(instituteId) && classMode !== "none",
  });

  // A single-institute user never sees the picker, so seed it from their own assignments.
  // Likewise an organisation admin running exactly one organisation.
  useEffect(() => {
    if (!choosesInstitute && user?.institute_ids.length === 1 && !form.getValues("institute_id")) {
      form.setValue("institute_id", user.institute_ids[0]!);
    }
    const myOrganisations = organisationIds(user);
    if (myOrganisations.length === 1 && !form.getValues("organisation_id")) {
      form.setValue("organisation_id", myOrganisations[0]!);
    }
  }, [choosesInstitute, user, form]);

  // Changing the role changes which fields apply; stale values would be submitted silently.
  useEffect(() => {
    if (!chosen) return;
    if (!needsBranch) form.setValue("branch_id", "");
    if (classMode === "none") form.setValue("class_ids", []);
  }, [chosen, needsBranch, classMode, form]);

  /** The scope fields depend on the role, so they are checked here rather than in zod. */
  const send = (values: Values) => {
    const missing: [keyof Values, string][] = [];
    if (needsOrganisation && !values.organisation_id)
      missing.push(["organisation_id", "Choose an organisation."]);
    if (needsInstitute && !values.institute_id)
      missing.push(["institute_id", "Choose an institute."]);
    if (needsBranch && !values.branch_id) missing.push(["branch_id", "Choose a branch."]);
    if (classMode === "required" && values.class_ids.length === 0)
      missing.push(["class_ids", "Choose at least one of your classes."]);
    if (missing.length > 0) {
      for (const [name, message] of missing) form.setError(name, { message });
      return;
    }
    submit.mutate({
      full_name: values.full_name,
      email: values.email,
      role_key: values.role_key as RoleKey,
      organisation_id: needsOrganisation ? values.organisation_id : undefined,
      institute_id: needsInstitute ? values.institute_id || undefined : undefined,
      branch_id: needsBranch ? values.branch_id || undefined : undefined,
      class_ids: values.class_ids.length ? values.class_ids : undefined,
    });
  };

  const submit = useMutation({
    mutationFn: inviteUser,
    onSuccess: async (result) => {
      await queryClient.invalidateQueries({ queryKey: userKeys.all });
      onInvited?.({
        name: result.user.full_name,
        email: result.user.email,
        invitationSent: result.invitation_sent,
        setupLink: result.setup_link,
      });
      form.reset();
      onClose();
    },
  });

  return (
    <Modal
      open={open}
      onClose={close}
      title="Invite a user"
      description="They get an email with a code to set their own password, and you get a one-time link you can share yourself."
      footer={
        <>
          <Button variant="secondary" onClick={close}>
            Cancel
          </Button>
          <Button form="invite-form" type="submit" loading={submit.isPending}>
            Send invitation
          </Button>
        </>
      }
    >
      <form id="invite-form" noValidate className="space-y-4" onSubmit={form.handleSubmit(send)}>
        {submit.error && (
          <Alert tone="danger" title="Could not send the invitation">
            <p>{submit.error.message}</p>
          </Alert>
        )}

        <TextField
          label="Full name"
          required
          autoFocus
          placeholder="Ravi Kumar"
          error={form.formState.errors.full_name?.message}
          {...form.register("full_name")}
        />

        <TextField
          label="Email address"
          type="email"
          required
          placeholder="ravi@example.com"
          error={form.formState.errors.email?.message}
          {...form.register("email")}
        />

        <SelectField
          label="Role"
          required
          placeholder={roles.isLoading ? "Loading roles…" : "Choose a role"}
          hint="You can only give roles below your own level."
          disabled={roles.isLoading}
          options={(roles.data ?? []).map((role) => ({ value: role.key, label: role.name }))}
          error={form.formState.errors.role_key?.message}
          {...form.register("role_key")}
        />

        {roles.data?.length === 0 && (
          <Alert tone="info">
            <p>You do not have permission to give out any roles.</p>
          </Alert>
        )}

        {needsOrganisation && (
          <SelectField
            label="Organisation"
            required
            placeholder={organisations.isLoading ? "Loading…" : "Choose an organisation"}
            hint={`${chosen?.name} applies across every institute in one organisation.`}
            disabled={organisations.isLoading}
            options={(organisations.data?.items ?? [])
              .filter((item) => item.status === "active")
              .map((item) => ({ value: item.id, label: `${item.name} (${item.code})` }))}
            error={form.formState.errors.organisation_id?.message}
            {...form.register("organisation_id")}
            // Controlled: it may be preselected before the options have arrived.
            value={organisationId}
          />
        )}

        {choosesInstitute && needsInstitute && (
          <SelectField
            label="Institute"
            required
            placeholder="Choose an institute"
            options={(institutes.data?.items ?? []).map((item) => ({
              value: item.id,
              label: `${item.name} (${item.code})`,
            }))}
            error={form.formState.errors.institute_id?.message}
            {...form.register("institute_id")}
          />
        )}

        {needsBranch && (
          <SelectField
            label="Branch"
            required
            placeholder={branches.isLoading ? "Loading branches…" : "Choose a branch"}
            hint="This role applies to one branch only."
            disabled={!instituteId || branches.isLoading}
            options={(branches.data?.items ?? []).map((item) => ({
              value: item.id,
              label: `${item.name} (${item.code})`,
            }))}
            error={form.formState.errors.branch_id?.message}
            {...form.register("branch_id")}
          />
        )}

        {classMode !== "none" && (
          <Field
            label="Classes"
            required={classMode === "required"}
            error={form.formState.errors.class_ids?.message}
            hint={
              classMode === "required"
                ? "Choose at least one of the classes you teach."
                : roleKey === "student"
                  ? "Choose the classes this student will join."
                  : "Choose the classes this teacher will take."
            }
          >
            {() => (
              <div className="max-h-44 space-y-1 overflow-y-auto rounded-lg border border-line p-2">
                {classes.isLoading && <p className="p-1 text-sm text-fg-2">Loading classes…</p>}
                {!classes.isLoading && (classes.data?.items.length ?? 0) === 0 && (
                  <p className="p-1 text-sm text-fg-2">No classes available yet.</p>
                )}
                {classes.data?.items.map((item) => (
                  <label
                    key={item.id}
                    className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-surface-2"
                  >
                    <input
                      type="checkbox"
                      value={item.id}
                      checked={selectedClasses.includes(item.id)}
                      onChange={(event) => {
                        const next = event.target.checked
                          ? [...selectedClasses, item.id]
                          : selectedClasses.filter((id) => id !== item.id);
                        form.setValue("class_ids", next, { shouldValidate: true });
                      }}
                      className="size-4 accent-[var(--primary)]"
                    />
                    <span className="text-fg">
                      {item.name}
                      {item.section ? ` — ${item.section}` : ""}
                    </span>
                  </label>
                ))}
              </div>
            )}
          </Field>
        )}
      </form>
    </Modal>
  );
}
