import { Link } from "react-router-dom";

import { Logo } from "@/components/Logo";

export function NotFoundPage() {
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-4 px-4 text-center">
      <Logo className="size-10" />
      <div className="space-y-1">
        <h1 className="text-2xl font-bold text-fg">Page not found</h1>
        <p className="text-sm text-fg-2">
          The page you were looking for does not exist or has moved.
        </p>
      </div>
      <Link
        to="/"
        className="inline-flex h-11 items-center rounded-lg bg-accent px-5 text-sm font-semibold text-accent-fg"
      >
        Go to dashboard
      </Link>
    </main>
  );
}
