import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { ThemeToggle } from "@/features/theme/ThemeToggle";
import { Logo } from "@/components/Logo";

/**
 * Shell for the signed-out pages.
 *
 * The brand panel is decorative and hidden below `lg`, where the form needs the full width.
 * The theme toggle does not persist here — there is no session to save it against yet.
 */
export function AuthLayout({
  title,
  description,
  children,
  footer,
}: {
  title: string;
  description?: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <div className="grid min-h-dvh lg:grid-cols-[1fr_minmax(0,32rem)]">
      <aside aria-hidden="true" className="relative hidden overflow-hidden bg-brand lg:block">
        <div className="flex h-full flex-col justify-between p-12">
          <Logo className="size-10" />

          <div className="max-w-md space-y-8">
            <p className="font-display text-4xl leading-tight font-extrabold text-white">
              One sign-in for every institute, branch and class.
            </p>
            <p className="text-sm leading-relaxed text-white/70">
              Admins manage their own part of the organisation. Faculty see their assigned classes.
              Students see their own learning. Each person gets exactly the access their role
              allows.
            </p>

            {/* The hierarchy, drawn. It explains the product's central idea faster than a
                paragraph does, and it is the one thing every new admin has to understand. */}
            <ol className="space-y-1.5">
              {[
                { level: "Platform", who: "Super Admin · Platform Admin", indent: 0 },
                { level: "Institute", who: "Institute Admin", indent: 1 },
                { level: "Branch", who: "Branch Admin", indent: 2 },
                { level: "Session", who: "2026–27", indent: 3 },
                { level: "Class", who: "Faculty · Student", indent: 4 },
              ].map((row) => (
                <li
                  key={row.level}
                  style={{ marginLeft: `${row.indent * 0.9}rem` }}
                  className={[
                    "flex items-center justify-between gap-4 rounded-sm px-3.5 py-2.5 text-xs",
                    row.indent === 4 ? "bg-accent text-white" : "bg-white/10 text-white/90",
                  ].join(" ")}
                >
                  <span className="font-semibold">{row.level}</span>
                  <span className={row.indent === 4 ? "text-white/90" : "text-white/60"}>
                    {row.who}
                  </span>
                </li>
              ))}
            </ol>
          </div>

          <p className="text-xs text-white/40">dhruvonlineacademy.com</p>
        </div>
      </aside>

      <main className="flex flex-col justify-center px-4 py-10 sm:px-8">
        <div className="mx-auto w-full max-w-sm">
          <div className="mb-8 flex items-center justify-between">
            <Link to="/" className="lg:hidden">
              <Logo />
            </Link>
            <div className="ml-auto">
              <ThemeToggle persist={false} />
            </div>
          </div>

          <div className="space-y-1.5">
            <h1 className="text-2xl font-bold tracking-tight text-fg">{title}</h1>
            {description && <p className="text-sm text-fg-2">{description}</p>}
          </div>

          <div className="mt-6">{children}</div>

          {footer && <div className="mt-6 text-center text-sm text-fg-2">{footer}</div>}
        </div>
      </main>
    </div>
  );
}
