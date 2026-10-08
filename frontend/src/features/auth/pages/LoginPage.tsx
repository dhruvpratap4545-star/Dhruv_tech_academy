import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { Alert } from "@/components/Alert";
import { Button } from "@/components/Button";
import { Checkbox, TextField } from "@/components/Field";
import { login } from "@/features/auth/api";
import { AuthLayout } from "@/features/auth/components/AuthLayout";
import type { LoginValues } from "@/features/auth/schemas";
import { loginSchema } from "@/features/auth/schemas";
import { useInvalidateMe } from "@/features/auth/useAuth";
import { ApiError } from "@/lib/api";

export function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const invalidateMe = useInvalidateMe();
  const from = (location.state as { from?: string } | null)?.from ?? "/";

  const form = useForm<LoginValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: "", password: "", remember_me: false },
  });

  const submit = useMutation({
    mutationFn: login,
    onSuccess: async () => {
      await invalidateMe();
      navigate(from, { replace: true });
    },
  });

  const error = submit.error;
  const locked = error instanceof ApiError && error.status === 429;

  return (
    <AuthLayout
      tabs
      title="Sign in"
      description="Use the email and password for your Dhruv Online Academy account."
    >
      <form
        noValidate
        className="space-y-4"
        onSubmit={form.handleSubmit((values) => submit.mutate(values))}
      >
        {error && (
          <Alert tone={locked ? "warning" : "danger"} title={locked ? "Account locked" : undefined}>
            <p>{error.message}</p>
          </Alert>
        )}

        {/* No required markers: every field on a sign-in form is required, so an asterisk
            on each one is decoration. The form is `noValidate` anyway — zod validates and
            writes a real message, which beats the browser's native bubble. */}
        <TextField
          label="Email"
          type="email"
          autoComplete="email"
          autoFocus
          placeholder="you@example.com"
          error={form.formState.errors.email?.message}
          {...form.register("email")}
        />

        <TextField
          label="Password"
          type="password"
          autoComplete="current-password"
          error={form.formState.errors.password?.message}
          action={
            <Link to="/forgot-password" className="text-xs font-medium text-accent hover:underline">
              Forgot password?
            </Link>
          }
          {...form.register("password")}
        />

        {/* States the duration. "On this device" told someone nothing about how long they
            would stay signed in, which is the only thing they are deciding. */}
        <Checkbox label="Keep me signed in for 30 days" {...form.register("remember_me")} />

        <Button type="submit" block size="lg" loading={submit.isPending}>
          Sign in
        </Button>
      </form>
    </AuthLayout>
  );
}
