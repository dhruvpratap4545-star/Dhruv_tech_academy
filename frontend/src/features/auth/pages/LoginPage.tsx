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
      title="Welcome back"
      description="Log in to your Dhruv Online Academy account."
      footer={
        <>
          New here?{" "}
          <Link to="/register" className="font-medium text-accent hover:underline">
            Create an account
          </Link>
        </>
      }
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

        <TextField
          label="Email address"
          type="email"
          autoComplete="email"
          autoFocus
          required
          placeholder="you@example.com"
          error={form.formState.errors.email?.message}
          {...form.register("email")}
        />

        <div className="space-y-1.5">
          <TextField
            label="Password"
            type="password"
            autoComplete="current-password"
            required
            error={form.formState.errors.password?.message}
            {...form.register("password")}
          />
          <div className="text-right">
            <Link to="/forgot-password" className="text-xs font-medium text-accent hover:underline">
              Forgot your password?
            </Link>
          </div>
        </div>

        <Checkbox label="Keep me logged in on this device" {...form.register("remember_me")} />

        <Button type="submit" block size="lg" loading={submit.isPending}>
          Log in
        </Button>
      </form>
    </AuthLayout>
  );
}
