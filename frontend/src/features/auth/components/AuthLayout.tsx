import type { ReactNode } from "react";
import { Link, NavLink } from "react-router-dom";

import { Logo } from "@/components/Logo";
import { ThemeToggle } from "@/features/theme/ThemeToggle";
import { cn } from "@/lib/cn";

/**
 * Shell for the signed-out pages.
 *
 * The geometry follows the client's wireframe exactly, because an earlier version did not
 * and the difference was the first thing anyone noticed:
 *
 * * **Two near-equal columns**, `1.05fr` and `1fr`. The previous version gave the form a
 *   fixed `32rem` and let the brand panel take everything else, so on a wide screen the
 *   split sat far right of centre, the form was squeezed against the edge, and the brand
 *   text drifted toward the middle to meet it.
 * * **The form is centred inside its own half**, horizontally and vertically, in a card of
 *   at most 400px. Centring is what makes the two halves read as a pair rather than as one
 *   panel with a sidebar.
 * * **The brand panel is `space-between`**: wordmark at the top, the message in the middle,
 *   the domain at the bottom, with the panel's own padding holding them off the edges.
 *
 * Below 860px — the wireframe's own breakpoint — the brand panel is gone and the form has
 * the screen to itself.
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
    <div className="grid min-h-dvh grid-cols-1 min-[860px]:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)]">
      <BrandPanel />

      <main className="relative flex items-center justify-center px-4 py-8 sm:px-6">
        <div className="absolute top-4 right-4 flex items-center gap-3">
          <Link to="/" className="min-[860px]:hidden" aria-label="Dhruv Online Academy">
            <Logo />
          </Link>
          <ThemeToggle persist={false} />
        </div>

        {/* 400px, as the wireframe specifies. Wider than this and a single-column form
            starts to look like a page with a lot of empty space in it. */}
        <div className="animate-rise grid w-full max-w-[400px] gap-5">
          <div className="space-y-1.5">
            <h1 className="font-display text-2xl font-bold tracking-tight text-fg">{title}</h1>
            {description && <p className="text-sm leading-relaxed text-fg-2">{description}</p>}
          </div>

          {tabs && <AuthTabs />}

          <div>{children}</div>

          {footer && <div className="text-center text-sm text-fg-2">{footer}</div>}
        </div>
      </main>
    </div>
  );
}

/** The navy half. Decorative, so it is hidden rather than reflowed on a narrow screen. */
function BrandPanel() {
  return (
    <aside
      aria-hidden="true"
      className="hidden flex-col justify-between gap-8 overflow-hidden bg-brand px-[clamp(1.25rem,4vw,3.5rem)] py-10 min-[860px]:flex"
    >
      <div className="animate-fade flex items-center gap-3">
        <Logo className="size-9" />
        <span className="font-display text-lg font-extrabold tracking-tight text-white">
          Dhruv Online Academy
        </span>
      </div>

      <div className="space-y-7">
        {/* `max-w-[22ch]` is the wireframe's measure. A headline wider than about
            twenty-two characters per line stops scanning as one phrase. */}
        <h2 className="animate-rise max-w-[22ch] font-display text-[clamp(1.5rem,2.6vw,2.1rem)] leading-[1.2] font-extrabold text-white">
          One sign-in for every institute, branch and class.
        </h2>
        <p className="animate-rise max-w-[48ch] text-sm leading-relaxed text-white/75 [animation-delay:60ms]">
          Administrators manage their own part of the organisation. Faculty see the classes they
          teach. Students see their own learning. Each person gets exactly the access their role
          allows.
        </p>

        {/* The hierarchy, drawn. It explains the product's central idea faster than a
            paragraph does, and it is the one thing every new administrator has to
            understand. Hidden on the wireframe's narrow layout along with this panel. */}
        <ol className="stagger grid max-w-[420px] gap-1.5">
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
              className={cn(
                "flex items-center justify-between gap-4 rounded-lg border px-3.5 py-2.5 text-xs",
                row.indent === 4
                  ? "border-teal-400/50 bg-teal-600/40 text-white"
                  : "border-white/12 bg-white/10 text-white/90",
              )}
            >
              <span className="font-display text-[0.74rem] font-bold tracking-[0.04em]">
                {row.level}
              </span>
              <span className="text-white/65">{row.who}</span>
            </li>
          ))}
        </ol>
      </div>

      <p className="text-xs text-white/40">dhruvonlineacademy.com</p>
    </aside>
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
    <nav aria-label="Sign in or sign up" className="flex gap-6 border-b border-line">
      <NavLink to="/login" className={({ isActive }) => tab(isActive)}>
        Sign in
      </NavLink>
      <NavLink to="/register" className={({ isActive }) => tab(isActive)}>
        Sign up
      </NavLink>
    </nav>
  );
}
