import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { useNavigate } from "react-router-dom";
import { z } from "zod";

import { Alert } from "@/components/Alert";
import { Button } from "@/components/Button";
import { Card, CardBody, CardHeader } from "@/components/Card";
import { PasswordStrength } from "@/features/auth/components/PasswordStrength";
import { TextField } from "@/components/Field";
import { PageHeader } from "@/components/PageHeader";
import { changePassword, updateProfile } from "@/features/auth/api";
import type { ChangePasswordValues } from "@/features/auth/schemas";
import { changePasswordSchema } from "@/features/auth/schemas";
import { useCurrentUser, useInvalidateMe } from "@/features/auth/useAuth";
import { ThemeToggle } from "@/features/theme/ThemeToggle";

const profileSchema = z.object({
  full_name: z.string().min(2, "Enter your full name.").max(120, "That name is too long."),
  phone: z
    .string()
    .trim()
    .max(20, "That number is too long.")
    .regex(/^[0-9+\-\s()]*$/, "Use digits and + - ( ) only."),
});

type ProfileValues = z.infer<typeof profileSchema>;

/**
 * Everything about your own account in one place: details, appearance, password.
 *
 * Previously split across /profile and /profile/password, which meant two clicks to change
 * a password and a page that existed only to hold one form.
 */
export function SettingsPage() {
  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Account"
        title="Settings"
        description="Your details, how the console looks, and your password."
      />
      <div className="grid gap-5 lg:grid-cols-2">
        <ProfileCard />
        <div className="space-y-5">
          <AppearanceCard />
          <PasswordCard />
        </div>
      </div>
    </div>
  );
}

function ProfileCard() {
  const user = useCurrentUser();
  const invalidateMe = useInvalidateMe();

  const form = useForm<ProfileValues>({
    resolver: zodResolver(profileSchema),
    // `values`, not `defaultValues`: /me may still be loading on first render.
    values: { full_name: user?.full_name ?? "", phone: user?.phone ?? "" },
  });

  const save = useMutation({
    mutationFn: (values: ProfileValues) =>
      updateProfile({ full_name: values.full_name, phone: values.phone || null }),
    onSuccess: () => invalidateMe(),
  });

  return (
    <Card>
      <CardHeader title="Your details" />
      <CardBody>
        <form
          noValidate
          className="space-y-4"
          onSubmit={form.handleSubmit((values) => save.mutate(values))}
        >
          {save.isSuccess && !form.formState.isDirty && (
            <Alert tone="success">
              <p>Your details have been saved.</p>
            </Alert>
          )}
          {save.error && (
            <Alert tone="danger">
              <p>{save.error.message}</p>
            </Alert>
          )}

          <TextField
            label="Full name"
            required
            error={form.formState.errors.full_name?.message}
            {...form.register("full_name")}
          />

          <TextField
            label="Phone number"
            type="tel"
            hint="Optional."
            placeholder="+91 98765 43210"
            error={form.formState.errors.phone?.message}
            {...form.register("phone")}
          />

          <div className="space-y-1">
            <p className="text-sm font-semibold text-fg">Email address</p>
            <p className="text-sm break-all text-fg-2">{user?.email}</p>
            <p className="text-xs text-fg-3">
              Your email is also your sign-in. Contact your administrator to change it.
            </p>
          </div>

          <Button type="submit" loading={save.isPending}>
            Save changes
          </Button>
        </form>
      </CardBody>
    </Card>
  );
}

function AppearanceCard() {
  return (
    <Card>
      <CardHeader
        title="Appearance"
        description="Saved to your account, so it follows you to any device."
      />
      <CardBody>
        <ThemeToggle />
      </CardBody>
    </Card>
  );
}

function PasswordCard() {
  const navigate = useNavigate();
  const invalidateMe = useInvalidateMe();

  const form = useForm<ChangePasswordValues>({
    resolver: zodResolver(changePasswordSchema),
    defaultValues: { current_password: "", new_password: "", confirm_password: "" },
  });

  const submit = useMutation({
    mutationFn: (values: ChangePasswordValues) =>
      changePassword({
        current_password: values.current_password,
        new_password: values.new_password,
      }),
    // Changing a password ends every session, including this one, so the only sensible
    // destination afterwards is the login page.
    onSuccess: async () => {
      await invalidateMe();
      navigate("/login", {
        replace: true,
        state: { notice: "Your password has been changed. Please log in again." },
      });
    },
  });

  return (
    <Card>
      <CardHeader
        title="Password"
        description="Changing it signs you out on this and every other device."
      />
      <CardBody>
        <form
          noValidate
          className="space-y-4"
          onSubmit={form.handleSubmit((values) => submit.mutate(values))}
        >
          {submit.error && (
            <Alert tone="danger">
              <p>{submit.error.message}</p>
            </Alert>
          )}

          <TextField
            label="Current password"
            type="password"
            autoComplete="current-password"
            required
            error={form.formState.errors.current_password?.message}
            {...form.register("current_password")}
          />

          <TextField
            label="New password"
            type="password"
            autoComplete="new-password"
            required
                error={form.formState.errors.new_password?.message}
            {...form.register("new_password")}
          />

          <PasswordStrength control={form.control} name="new_password" />

          <TextField
            label="Confirm new password"
            type="password"
            autoComplete="new-password"
            required
            error={form.formState.errors.confirm_password?.message}
            {...form.register("confirm_password")}
          />

          <Button type="submit" loading={submit.isPending}>
            Change password
          </Button>
        </form>
      </CardBody>
    </Card>
  );
}
