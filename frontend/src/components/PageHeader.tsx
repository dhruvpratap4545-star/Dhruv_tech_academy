import type { ReactNode } from "react";

/**
 * Page title block: a small eyebrow for the section, the title, a sentence of context,
 * and the primary action. The eyebrow is what tells someone which part of the console
 * they are in once the sidebar is a drawer.
 */
export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <header className="flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0 space-y-1">
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h1 className="font-display text-2xl font-extrabold tracking-tight text-fg">{title}</h1>
        {description && <p className="max-w-2xl text-sm text-fg-2">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}
