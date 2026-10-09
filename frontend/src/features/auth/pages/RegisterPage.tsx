import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { Link, useNavigate } from "react-router-dom";

import { Alert } from "@/components/Alert";
import { Button } from "@/components/Button";
import { Checkbox, TextField } from "@/components/Field";
import { register as registerAccount } from "@/features/auth/api";
import { AuthLayout } from "@/features/auth/components/AuthLayout";
import { PasswordStrength } from "@/features/auth/components/PasswordStrength";
import type { RegisterValues } from "@/features/auth/schemas";
import { registerSchema } from "@/features/auth/schemas";
import { useInvalidateMe } from "@/features/auth/useAuth";

/**
 * Direct Learner sign-up (PRD §4.1).
 *
 * Consent is a hard requirement, not a pre-ticked convenience: under the DPDP Act it has to
 * be a positive action, and the backend refuses the request without it.
 */
export function RegisterPage() {
  const navigate = useNavigate();
  const invalidateMe = useInvalidateMe();

  const form = useForm<RegisterValues>({
    resolver: zodResolver(registerSchema),
    defaultValues: { full_name: "", email: "", password: "", accept_terms: false as true },
  });

  const submit = useMutation({
    mutationFn: registerAccount,
    onSuccess: async () => {
      await invalidateMe();
      navigate("/", { replace: true });
    },
  });

  return (
    <AuthLayout
      tabs
      title="Create your account"
      description="For learners joining Dhruv Online Academy directly."
      footer={
        <>
          Already have an account?{" "}
          <Link to="/login" className="font-medium text-accent hover:underline">
            Log in
          </Link>
        </>
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
          label="Full name"
          autoComplete="name"
          autoFocus
          required
          placeholder="Asha Rao"
          error={form.formState.errors.full_name?.message}
          {...form.register("full_name")}
        />

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
          label="Password"
          type="password"
          autoComplete="new-password"
          required
            error={form.formState.errors.password?.message}
          {...form.register("password")}
        />

        <PasswordStrength control={form.control} name="password" />

        <Checkbox
          error={form.formState.errors.accept_terms?.message}
          label={
            <>
              I am 18 or older and I accept the{" "}
              <a href="/terms" className="font-medium text-accent hover:underline">
                Terms of Use
              </a>{" "}
              and{" "}
              <a href="/privacy" className="font-medium text-accent hover:underline">
                Privacy Policy
              </a>
              .
            </>
          }
          {...form.register("accept_terms")}
        />

        <Button type="submit" block size="lg" loading={submit.isPending}>
          Create account
        </Button>

        <p className="text-center text-xs text-fg-2">
          Studying with a school, college or coaching institute? They will invite you by email.
        </p>
      </form>
    </AuthLayout>
  );
}
