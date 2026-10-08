import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { ThemeToggle } from "@/features/theme/ThemeToggle";
import { Logo } from "@/components/Logo";
import { NavLink } from "react-router-dom";
import { cn } from "@/lib/cn";

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
  tabs = false,
}: {
  title: string;
  description?: string;
  children: ReactNode;
  footer?: ReactNode;
  /** Shows the Sign in / Sign up pair, as the client's wireframe does. */
  tabs?: boolean;
}) {
  return (
    <div className="grid min-h-dvh lg:grid-cols-[1fr_minmax(0,32rem)]">
      <aside aria-hidden="true" className="relative hidden overflow-hidden bg-brand lg:block">
        <div className="flex h-full flex-col justify-between p-12">
          <div className="flex items-center gap-3">
            <Logo className="size-10" />
            <span className="font-display text-lg font-extrabold tracking-tight text-white">
              Dhruv Online Academy
            </span>
          </div>

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

      <main className="relative flex flex-col justify-center px-4 py-10 sm:px-8">
        <div className="absolute top-5 right-5 flex items-center gap-3">
          <Link to="/" className="lg:hidden" aria-label="Dhruv Online Academy">
            <Logo />
          </Link>
          <ThemeToggle persist={false} />
        </div>

        <div className="mx-auto w-full max-w-sm">
          <div className="space-y-1.5">
            <h1 className="font-display text-2xl font-bold tracking-tight text-fg">{title}</h1>
            {description && <p className="text-sm text-fg-2">{description}</p>}
          </div>

          {tabs && <AuthTabs />}

          <div className="mt-6">{children}</div>

          {footer && <div className="mt-6 text-center text-sm text-fg-2">{footer}</div>}
        </div>
      </main>
    </div>
  );
}

/**
 * Sign in / Sign up, as two routes rather than a toggle.
 *
 * The wireframe shows them as tabs and it is the better affordance: both options are
 * visible at once, so a new learner is not hunting for the sign-up link at the bottom of
 * a form they cannot complete.
 */
function AuthTabs() {
  const tab = (active: boolean) =>
    cn(
      "-mb-px border-b-2 px-1 pb-2.5 text-sm font-semibold transition-colors",
      active
        ? "border-accent text-fg"
        : "border-transparent text-fg-3 hover:border-line-strong hover:text-fg-2",
    );

  return (
    <nav aria-label="Sign in or sign up" className="mt-5 flex gap-6 border-b border-line">
      <NavLink to="/login" className={({ isActive }) => tab(isActive)}>
        Sign in
      </NavLink>
      <NavLink to="/register" className={({ isActive }) => tab(isActive)}>
        Sign up
      </NavLink>
    </nav>
  );
}
