import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";

import { PageHeader } from "@/components/PageHeader";
import { useCan } from "@/features/auth/useAuth";
import { LanguageToggle } from "@/features/i18n/LanguageToggle";
import { useT } from "@/features/i18n/useT";
import type { MessageKey } from "@/lib/i18n";
import type { Permission } from "@/lib/permissions";
import { cn } from "@/lib/cn";

const TABS: { to: string; label: MessageKey; permission: Permission }[] = [
  { to: "/library", label: "library.nav.library", permission: "library:read" },
  { to: "/library/review", label: "library.nav.review", permission: "library:contribute" },
  { to: "/library/manage", label: "library.nav.manage", permission: "library:manage" },
];

/** Page frame for the library screens, with tabs for whichever of them the person may use. */
export function LibraryLayout({
  title,
  description,
  actions,
  children,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  const { t } = useT();
  const allowed = {
    "library:read": useCan("library:read"),
    "library:contribute": useCan("library:contribute"),
    "library:manage": useCan("library:manage"),
  } as Record<Permission, boolean>;
  const tabs = TABS.filter((tab) => allowed[tab.permission]);
  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow={t("library.eyebrow")}
        title={title}
        description={description}
        actions={
          <>
            {actions}
            <LanguageToggle />
          </>
        }
      />
      {tabs.length > 1 && (
        <nav aria-label={t("library.eyebrow")} className="-mx-1 flex gap-1 overflow-x-auto pb-1">
          {tabs.map((tab) => (
            <NavLink
              key={tab.to}
              to={tab.to}
              end
              className={({ isActive }) =>
                cn(
                  "rounded-lg px-3 py-2 text-sm font-medium whitespace-nowrap",
                  isActive
                    ? "bg-accent text-accent-fg"
                    : "text-fg-2 hover:bg-surface-2 hover:text-fg",
                )
              }
            >
              {t(tab.label)}
            </NavLink>
          ))}
        </nav>
      )}
      {children}
    </div>
  );
}
