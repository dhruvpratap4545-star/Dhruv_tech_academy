import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";

import { Alert } from "@/components/Alert";
import { Button } from "@/components/Button";
import { Field, SelectField, TextField } from "@/components/Field";
import { Modal } from "@/components/Modal";
import { fetchAssignableRoles } from "@/features/auth/api";
import { email as emailSchema } from "@/features/auth/schemas";
import type { RoleKey } from "@/features/auth/types";
import { useCurrentUser } from "@/features/auth/useAuth";
import { isPlatformStaff, ROLE_REQUIREMENTS } from "@/lib/permissions";
import {
  fetchBranches,
  fetchClasses,
  fetchInstitutes,
  instituteKeys,
  inviteUser,
  userKeys,
} from "@/features/admin/api";

const schema = z.object({
  full_name: z.string().min(2, "Enter their full name.").max(120, "That name is too long."),
  email: emailSchema,
  role_key: z.string().min(1, "Please choose a role."),
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
 */
export function InviteUserModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const user = useCurrentUser();
  const queryClient = useQueryClient();
  const platformStaff = isPlatformStaff(user);

  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      full_name: "",
      email: "",
      role_key: "",
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
  const instituteId = useWatch({ control, name: "institute_id" }) ?? "";
  const branchId = useWatch({ control, name: "branch_id" }) ?? "";
  const selectedClasses = useWatch({ control, name: "class_ids" }) ?? [];
  const requirements = roleKey ? ROLE_REQUIREMENTS[roleKey] : null;

  const roles = useQuery({
    queryKey: ["assignable-roles"],
    queryFn: fetchAssignableRoles,
    enabled: open,
  });

  // Platform staff pick an institute; everyone else is pinned to their own, so the field
  // is not shown and the value is filled in from /me.
  const institutes = useQuery({
    queryKey: instituteKeys.list(),
    queryFn: ({ signal }) => fetchInstitutes(signal),
    enabled: open && platformStaff,
  });

  const branches = useQuery({
    queryKey: instituteKeys.branches(instituteId),
    queryFn: ({ signal }) => fetchBranches(instituteId, signal),
    enabled: open && Boolean(instituteId) && Boolean(requirements?.branch),
  });

  const classes = useQuery({
    queryKey: instituteKeys.classes(instituteId, branchId || undefined),
    queryFn: ({ signal }) => fetchClasses(instituteId, branchId || undefined, signal),
    enabled: open && Boolean(instituteId) && requirements?.classes !== "none",
  });

  // A single-institute user never sees the picker, so seed it from their own assignments.
  useEffect(() => {
    if (!platformStaff && user?.institute_ids.length === 1 && !form.getValues("institute_id")) {
      form.setValue("institute_id", user.institute_ids[0]!);
    }
  }, [platformStaff, user, form]);

  // Changing the role changes which fields apply; stale values would be submitted silently.
  useEffect(() => {
    if (requirements && !requirements.branch) form.setValue("branch_id", "");
    if (requirements?.classes === "none") form.setValue("class_ids", []);
  }, [requirements, form]);

  const submit = useMutation({
    mutationFn: inviteUser,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: userKeys.all });
      form.reset();
      onClose();
    },
  });

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Invite a user"
      description="They will get an email with a code to set their own password."
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button form="invite-form" type="submit" loading={submit.isPending}>
            Send invitation
          </Button>
        </>
      }
    >
      <form
        id="invite-form"
        noValidate
        className="space-y-4"
        onSubmit={form.handleSubmit((values) =>
          submit.mutate({
            full_name: values.full_name,
            email: values.email,
            role_key: values.role_key as RoleKey,
            institute_id: values.institute_id || undefined,
            branch_id: values.branch_id || undefined,
            class_ids: values.class_ids.length ? values.class_ids : undefined,
          }),
        )}
      >
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

        {platformStaff && requirements?.institute && (
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

        {requirements?.branch && (
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

        {requirements && requirements.classes !== "none" && (
          <Field
            label="Classes"
            hint={
              roleKey === "student"
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
                        form.setValue("class_ids", next);
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
