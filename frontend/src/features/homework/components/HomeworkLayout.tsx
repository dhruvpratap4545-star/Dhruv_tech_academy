import type { ReactNode } from "react";

import { PageHeader } from "@/components/PageHeader";
import { LanguageToggle } from "@/features/i18n/LanguageToggle";
import { useT } from "@/features/i18n/useT";

/** Page header shared by every homework screen, with the English / हिन्दी toggle. */
export function HomeworkLayout({
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
  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow={t("homework.eyebrow")}
        title={title}
        description={description}
        actions={
          <>
            {actions}
            <LanguageToggle />
          </>
        }
      />
      {children}
    </div>
  );
}
