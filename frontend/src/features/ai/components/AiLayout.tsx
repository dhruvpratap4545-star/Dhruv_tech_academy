import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";

import { PageHeader } from "@/components/PageHeader";
import { useCan } from "@/features/auth/useAuth";
import { LanguageToggle } from "@/features/i18n/LanguageToggle";
import { useT } from "@/features/i18n/useT";
import type { MessageKey } from "@/lib/i18n";
import { cn } from "@/lib/cn";

const TABS: { to: string; label: MessageKey; manageOnly: boolean }[] = [
  { to: "/ai", label: "ai.nav.dashboard", manageOnly: false },
  { to: "/ai/budgets", label: "ai.nav.budgets", manageOnly: false },
  { to: "/ai/usage", label: "ai.nav.usage", manageOnly: false },
  { to: "/ai/models", label: "ai.nav.models", manageOnly: true },
  { to: "/ai/features", label: "ai.nav.features", manageOnly: true },
  { to: "/ai/playground", label: "ai.nav.playground", manageOnly: true },
];

/** The Control Room's own tabs. Institute admins see the first three; platform staff all. */
export function AiLayout({
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
  const canManage = useCan("ai:manage");
  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow={t("ai.eyebrow")}
        title={title}
        description={description}
        actions={
          <>
            {actions}
            <LanguageToggle />
          </>
        }
      />
      <nav aria-label={t("ai.eyebrow")} className="-mx-1 flex gap-1 overflow-x-auto pb-1">
        {TABS.filter((tab) => canManage || !tab.manageOnly).map((tab) => (
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
      {children}
    </div>
  );
}
