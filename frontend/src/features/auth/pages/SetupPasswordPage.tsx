import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { Alert } from "@/components/Alert";
import { Button } from "@/components/Button";
import { TextField } from "@/components/Field";
import { setupPassword } from "@/features/auth/api";
import { AuthLayout } from "@/features/auth/components/AuthLayout";
import { PasswordStrength } from "@/features/auth/components/PasswordStrength";
import type { SetupValues } from "@/features/auth/schemas";
import { setupSchema } from "@/features/auth/schemas";

/**
 * First password for an invited user (PRD §4.2).
 *
 * The email can arrive as `?email=` so the person does not have to retype it. The code is
 * never pre-filled from the URL: a link that completes the whole flow would make forwarding
 * the invitation email equivalent to handing over the account.
 */
export function SetupPasswordPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();

  const form = useForm<SetupValues>({
    resolver: zodResolver(setupSchema),
    defaultValues: {
      email: params.get("email") ?? "",
      code: "",
      new_password: "",
      confirm_password: "",
    },
  });

  const submit = useMutation({
    mutationFn: (values: SetupValues) =>
      setupPassword({ email: values.email, code: values.code, new_password: values.new_password }),
    onSuccess: () =>
      navigate("/login", {
        replace: true,
        state: { notice: "Your password is set. Please log in." },
      }),
  });

  return (
    <AuthLayout
      title="Set your password"
      description="Use the 6-digit code from your invitation email."
      footer={
        <Link to="/login" className="font-medium text-accent hover:underline">
          Back to log in
        </Link>
      }
    >
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
          label="Email address"
          type="email"
          autoComplete="email"
          required
          placeholder="you@example.com"
          error={form.formState.errors.email?.message}
          {...form.register("email")}
        />

        <TextField
          label="6-digit code"
          inputMode="numeric"
          autoComplete="one-time-code"
          maxLength={6}
          required
          placeholder="123456"
          className="text-center text-lg tracking-[0.5em]"
          error={form.formState.errors.code?.message}
          {...form.register("code")}
        />

        <TextField
          label="Create a password"
          type="password"
          autoComplete="new-password"
          required
            error={form.formState.errors.new_password?.message}
          {...form.register("new_password")}
        />

        <PasswordStrength control={form.control} name="new_password" />

        <TextField
          label="Confirm password"
          type="password"
          autoComplete="new-password"
          required
          error={form.formState.errors.confirm_password?.message}
          {...form.register("confirm_password")}
        />

        <Button type="submit" block size="lg" loading={submit.isPending}>
          Set password
        </Button>
      </form>
    </AuthLayout>
  );
}
