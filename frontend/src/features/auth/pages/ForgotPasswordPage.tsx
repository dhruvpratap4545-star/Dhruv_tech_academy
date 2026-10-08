import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { Alert } from "@/components/Alert";
import { Button } from "@/components/Button";
import { TextField } from "@/components/Field";
import { forgotPassword, resetPassword, verifyOtp } from "@/features/auth/api";
import { AuthLayout } from "@/features/auth/components/AuthLayout";
import type { ForgotValues, NewPasswordValues, OtpValues } from "@/features/auth/schemas";
import { forgotSchema, newPasswordSchema, otpSchema } from "@/features/auth/schemas";

const RESEND_COOLDOWN_SECONDS = 60;

type Step = "email" | "code" | "password";

/**
 * Forgot password in three steps (PRD §4.4): email → 6-digit code → new password.
 *
 * Kept as one route with internal state rather than three URLs, because the reset token
 * from step two must not end up in a browser history entry or a shared link.
 */
export function ForgotPasswordPage() {
  const navigate = useNavigate();

  // The reset email links here with `?email=`, meaning "you already have a code". Start on
  // the code step rather than the first one: sending them back to step one would issue a
  // second code and silently invalidate the one they are holding.
  const [params] = useSearchParams();
  const linkedEmail = params.get("email") ?? "";

  const [step, setStep] = useState<Step>(linkedEmail ? "code" : "email");
  const [email, setEmail] = useState(linkedEmail);
  const [resetToken, setResetToken] = useState("");

  return (
    <AuthLayout
      title={
        step === "email"
          ? "Reset your password"
          : step === "code"
            ? "Check your email"
            : "Choose a new password"
      }
      description={
        step === "email"
          ? "We will email you a 6-digit code."
          : step === "code"
            ? `We sent a code to ${email}. It is valid for 10 minutes.`
            : "You will be logged out on all other devices."
      }
      footer={
        <Link to="/login" className="font-medium text-accent hover:underline">
          Back to log in
        </Link>
      }
    >
      <ol className="mb-6 flex items-center gap-2" aria-label="Progress">
        {(["email", "code", "password"] as const).map((name, index) => {
          const current = ["email", "code", "password"].indexOf(step);
          const done = index < current;
          const active = index === current;
          return (
            <li key={name} className="flex flex-1 items-center gap-2">
              <span
                aria-current={active ? "step" : undefined}
                className={[
                  "flex size-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold",
                  done || active ? "bg-accent text-accent-fg" : "bg-surface-3 text-fg-3",
                ].join(" ")}
              >
                {done ? "✓" : index + 1}
              </span>
              {index < 2 && (
                <span className={["h-px flex-1", done ? "bg-accent" : "bg-line"].join(" ")} />
              )}
            </li>
          );
        })}
      </ol>

      {step === "email" && (
        <EmailStep
          onSent={(value) => {
            setEmail(value);
            setStep("code");
          }}
        />
      )}
      {step === "code" && (
        <CodeStep
          email={email}
          onVerified={(token) => {
            setResetToken(token);
            setStep("password");
          }}
        />
      )}
      {step === "password" && (
        <PasswordStep
          resetToken={resetToken}
          onDone={() =>
            navigate("/login", {
              replace: true,
              state: { notice: "Your password has been changed. Please log in." },
            })
          }
        />
      )}
    </AuthLayout>
  );
}

function EmailStep({ onSent }: { onSent: (email: string) => void }) {
  const form = useForm<ForgotValues>({
    resolver: zodResolver(forgotSchema),
    defaultValues: { email: "" },
  });

  const submit = useMutation({
    mutationFn: forgotPassword,
    // The API answers identically whether or not the address exists, so the UI moves on
    // regardless — showing "no such account" here would leak who has one.
    onSuccess: (_, variables) => onSent(variables.email),
  });

  return (
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
        autoFocus
        required
        placeholder="you@example.com"
        error={form.formState.errors.email?.message}
        {...form.register("email")}
      />
      <Button type="submit" block size="lg" loading={submit.isPending}>
        Send code
      </Button>
    </form>
  );
}

function CodeStep({ email, onVerified }: { email: string; onVerified: (token: string) => void }) {
  const [secondsLeft, setSecondsLeft] = useState(RESEND_COOLDOWN_SECONDS);

  // Mirrors the server's 60-second resend cooldown (PRD §7.3), so the button is disabled
  // rather than returning 429 when someone taps it twice.
  useEffect(() => {
    if (secondsLeft <= 0) return;
    const timer = setTimeout(() => setSecondsLeft((value) => value - 1), 1000);
    return () => clearTimeout(timer);
  }, [secondsLeft]);

  const form = useForm<OtpValues>({
    resolver: zodResolver(otpSchema),
    defaultValues: { code: "" },
  });

  const verify = useMutation({
    mutationFn: (values: OtpValues) => verifyOtp({ email, code: values.code }),
    onSuccess: (data) => onVerified(data.reset_token),
  });

  const resend = useMutation({
    mutationFn: () => forgotPassword({ email }),
    onSuccess: () => setSecondsLeft(RESEND_COOLDOWN_SECONDS),
  });

  return (
    <form
      noValidate
      className="space-y-4"
      onSubmit={form.handleSubmit((values) => verify.mutate(values))}
    >
      {verify.error && (
        <Alert tone="danger">
          <p>{verify.error.message}</p>
        </Alert>
      )}
      {resend.isSuccess && !verify.error && (
        <Alert tone="success">
          <p>A new code is on its way.</p>
        </Alert>
      )}

      <TextField
        label="6-digit code"
        inputMode="numeric"
        autoComplete="one-time-code"
        maxLength={6}
        autoFocus
        required
        placeholder="123456"
        className="text-center text-lg tracking-[0.5em]"
        error={form.formState.errors.code?.message}
        {...form.register("code")}
      />

      <Button type="submit" block size="lg" loading={verify.isPending}>
        Verify code
      </Button>

      <Button
        type="button"
        variant="ghost"
        block
        disabled={secondsLeft > 0 || resend.isPending}
        onClick={() => resend.mutate()}
      >
        {secondsLeft > 0 ? `Resend code in ${secondsLeft}s` : "Resend code"}
      </Button>
    </form>
  );
}

function PasswordStep({ resetToken, onDone }: { resetToken: string; onDone: () => void }) {
  const form = useForm<NewPasswordValues>({
    resolver: zodResolver(newPasswordSchema),
    defaultValues: { new_password: "", confirm_password: "" },
  });

  const submit = useMutation({
    mutationFn: (values: NewPasswordValues) =>
      resetPassword({ reset_token: resetToken, new_password: values.new_password }),
    onSuccess: onDone,
  });

  return (
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
        label="New password"
        type="password"
        autoComplete="new-password"
        autoFocus
        required
        hint="At least 8 characters, with one letter and one number."
        error={form.formState.errors.new_password?.message}
        {...form.register("new_password")}
      />

      <TextField
        label="Confirm new password"
        type="password"
        autoComplete="new-password"
        required
        error={form.formState.errors.confirm_password?.message}
        {...form.register("confirm_password")}
      />

      <Button type="submit" block size="lg" loading={submit.isPending}>
        Change password
      </Button>
    </form>
  );
}
